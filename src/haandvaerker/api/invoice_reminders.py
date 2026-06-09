"""Invoice reminder API — send rykkere to customers with unpaid invoices."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..config import REMINDER_FEE_ORE_1, REMINDER_FEE_ORE_2, REMINDER_FEE_ORE_3
from ..dependencies import CompanyContextDep
from ..models.customer import Customer
from ..models.invoice import Invoice, InvoiceStatus
from ..models.invoice_reminder import InvoiceReminder, InvoiceReminderRead
from ..services.config_resolver import resolve_email_config
from ..services.invoice_reminder_service import send_or_generate_reminder

router = APIRouter(prefix="/invoice-reminders", tags=["invoice-reminders"])


# ── Request / response models ─────────────────────────────────────────────────

class SendReminderRequest(BaseModel):
    invoice_id: str
    level: int          # 1 | 2 | 3
    fee_ore: Optional[int] = None   # None → use default from config
    sent_by: str = "user"


class SendReminderResponse(BaseModel):
    reminder: InvoiceReminderRead
    method: str         # "email" | "manual" | "failed"
    smtp_configured: bool
    smtp_error: Optional[str]
    message: str


class OverdueInvoiceRow(BaseModel):
    invoice_id: str
    invoice_number: str
    customer_id: str
    customer_name: str
    customer_email: Optional[str]
    due_date: date
    days_overdue: int
    total: float
    next_reminder_level: int    # 1, 2, or 3 (4 = all sent)
    reminders_sent: list[int]   # e.g. [1, 2]


class ReminderConfigResponse(BaseModel):
    smtp_configured: bool
    smtp_host: str
    fee_ore_1: int
    fee_ore_2: int
    fee_ore_3: int


# ── 1. GET /invoice-reminders/config ─────────────────────────────────────────

@router.get("/config", response_model=ReminderConfigResponse)
def get_reminder_config(ctx: CompanyContextDep) -> ReminderConfigResponse:
    email_cfg = resolve_email_config(ctx.session, ctx.company_id)
    smtp_configured = email_cfg is not None
    smtp_host = email_cfg.smtp_host if email_cfg else "(ikke konfigureret)"
    return ReminderConfigResponse(
        smtp_configured=smtp_configured,
        smtp_host=smtp_host,
        fee_ore_1=REMINDER_FEE_ORE_1,
        fee_ore_2=REMINDER_FEE_ORE_2,
        fee_ore_3=REMINDER_FEE_ORE_3,
    )


# ── 2. GET /invoice-reminders/overdue ────────────────────────────────────────

@router.get("/overdue", response_model=list[OverdueInvoiceRow])
def list_overdue_invoices(ctx: CompanyContextDep) -> list[OverdueInvoiceRow]:
    """Return all sent (unpaid) invoices past due date, enriched with reminder history."""
    session = ctx.session
    company_id = ctx.company_id

    today = date.today()
    invoices = session.exec(
        select(Invoice).where(
            Invoice.company_id == company_id,
            Invoice.status == InvoiceStatus.sent,
            Invoice.active == True,  # noqa: E712
            Invoice.due_date < today,
        )
    ).all()

    rows: list[OverdueInvoiceRow] = []
    for inv in invoices:
        customer = session.get(Customer, inv.customer_id)
        if not customer:
            continue

        sent_levels = [
            r.level for r in session.exec(
                select(InvoiceReminder).where(InvoiceReminder.invoice_id == inv.id)
            ).all()
        ]
        next_level = max(sent_levels) + 1 if sent_levels else 1
        days_overdue = (today - inv.due_date).days

        rows.append(OverdueInvoiceRow(
            invoice_id=inv.id,
            invoice_number=inv.invoice_number,
            customer_id=inv.customer_id,
            customer_name=customer.name,
            customer_email=customer.email,
            due_date=inv.due_date,
            days_overdue=days_overdue,
            total=inv.total,
            next_reminder_level=next_level,
            reminders_sent=sorted(sent_levels),
        ))

    rows.sort(key=lambda r: r.days_overdue, reverse=True)
    return rows


# ── 3. POST /invoice-reminders/send ──────────────────────────────────────────

@router.post("/send", response_model=SendReminderResponse, status_code=201)
def send_reminder(body: SendReminderRequest, ctx: CompanyContextDep) -> SendReminderResponse:
    """Send or generate a reminder for an invoice at a given level."""
    session = ctx.session
    # Validate invoice belongs to session company
    invoice = session.get(Invoice, body.invoice_id)
    if not invoice:
        raise HTTPException(status_code=422, detail=f"Faktura '{body.invoice_id}' ikke fundet")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    default_fees = {1: REMINDER_FEE_ORE_1, 2: REMINDER_FEE_ORE_2, 3: REMINDER_FEE_ORE_3}
    fee_ore = body.fee_ore if body.fee_ore is not None else default_fees.get(body.level, 0)

    try:
        result = send_or_generate_reminder(
            session=session,
            invoice_id=body.invoice_id,
            level=body.level,
            fee_ore=fee_ore,
            sent_by=body.sent_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    method_msgs = {
        "email": f"Rykker sendt via email til {result.reminder.email_to}",
        "manual": "Rykkertekst genereret — send manuelt (SMTP ikke konfigureret eller ingen email på kunden)",
        "failed": f"SMTP-afsendelse fejlede — tekst gemt til manuel afsendelse. Fejl: {result.smtp_error}",
    }

    email_cfg = resolve_email_config(session, ctx.company_id)
    return SendReminderResponse(
        reminder=InvoiceReminderRead.model_validate(result.reminder),
        method=result.method,
        smtp_configured=email_cfg is not None,
        smtp_error=result.smtp_error,
        message=method_msgs.get(result.method, result.method),
    )


# ── 4. GET /invoice-reminders/history ────────────────────────────────────────

@router.get("/history", response_model=list[InvoiceReminderRead])
def get_reminder_history(invoice_id: str, ctx: CompanyContextDep) -> list[InvoiceReminderRead]:
    """Return all reminders sent for a specific invoice, ordered by level."""
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=422, detail=f"Faktura '{invoice_id}' ikke fundet")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    reminders = session.exec(
        select(InvoiceReminder)
        .where(InvoiceReminder.invoice_id == invoice_id)
        .order_by(InvoiceReminder.level)
    ).all()
    return [InvoiceReminderRead.model_validate(r) for r in reminders]
