"""Invoice reminder service — generates text and optionally sends via SMTP."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from sqlmodel import Session, select

from ..config import REMINDER_FEE_ORE_1, REMINDER_FEE_ORE_2, REMINDER_FEE_ORE_3
from ..models.company import Company
from ..models.customer import Customer
from ..models.invoice import Invoice, InvoiceStatus
from ..models.invoice_reminder import InvoiceReminder
from ..services.config_resolver import resolve_email_config
from ..services.smtp_sender import (
    SmtpNotConfiguredError,
    SmtpSendError,
    send_email,
)


# ── Reminder text templates (Danish) ─────────────────────────────────────────

_LEVEL_LABELS = {1: "1. rykker", 2: "2. rykker", 3: "Inkassovarsel"}

_SUBJECT_TEMPLATES = {
    1: "Venlig påmindelse — faktura {inv_number} forfalden {due_date}",
    2: "2. rykker — faktura {inv_number}, stadig ubetalt",
    3: "INKASSOVARSEL — faktura {inv_number}",
}

_BODY_TEMPLATES = {
    1: """\
Kære {customer_name},

Vi tillader os venligst at minde om nedenstående faktura, som endnu ikke ses registreret betalt.

  Faktura nr.:      {inv_number}
  Forfaldsdato:     {due_date}
  Beløb inkl. moms: {total} kr

Hvis betalingen allerede er afsendt, bedes du se bort fra denne påmindelse.

Er der spørgsmål til fakturaen, er du altid velkommen til at kontakte os.

Med venlig hilsen
{company_name}
{company_contact}
""",
    2: """\
Kære {customer_name},

Vi har endnu ikke modtaget betaling for nedenstående faktura. Dette er vores 2. rykker.

  Faktura nr.:      {inv_number}
  Forfaldsdato:     {due_date}
  Beløb inkl. moms: {total} kr{fee_line}

Vi anmoder venligst om, at betalingen sker inden 8 dage.

Har du spørgsmål, kontakt os venligst hurtigst muligt.

Med venlig hilsen
{company_name}
{company_contact}
""",
    3: """\
Kære {customer_name},

På trods af tidligere rykkere har vi fortsat ikke modtaget betaling.

  Faktura nr.:      {inv_number}
  Forfaldsdato:     {due_date}
  Skyldigt beløb:   {total} kr{fee_line}

Betaling skal være os i hænde inden 5 dage fra dags dato.

Sker betaling ikke, vil kravet uden yderligere varsel blive overgivet til inkasso.

Med venlig hilsen
{company_name}
{company_contact}
""",
}


def _fmt_kr(amount_float: float) -> str:
    """Format float as Danish decimal string, e.g. 1234.5 → '1.234,50'"""
    return f"{amount_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fee_line(fee_ore: int) -> str:
    if fee_ore <= 0:
        return ""
    return f"\n  Rykkergebyr:      {_fmt_kr(fee_ore / 100)} kr"


def generate_reminder(
    invoice: Invoice,
    customer: Customer,
    company: Company,
    level: int,
    fee_ore: int,
) -> tuple[str, str]:
    """Return (subject, body_text) for the given reminder level."""
    due_str = invoice.due_date.strftime("%d-%m-%Y") if invoice.due_date else "—"
    company_contact = " | ".join(filter(None, [company.phone, company.email, company.address]))

    ctx = {
        "customer_name": customer.name,
        "inv_number": invoice.invoice_number,
        "due_date": due_str,
        "total": _fmt_kr(invoice.total),
        "fee_line": _fee_line(fee_ore),
        "company_name": company.name,
        "company_contact": company_contact or company.name,
    }
    subject = _SUBJECT_TEMPLATES[level].format(**ctx)
    body = _BODY_TEMPLATES[level].format(**ctx)
    return subject, body


# ── Main service function ─────────────────────────────────────────────────────

class ReminderResult:
    def __init__(
        self,
        reminder: InvoiceReminder,
        method: str,
        smtp_error: Optional[str] = None,
    ) -> None:
        self.reminder = reminder
        self.method = method
        self.smtp_error = smtp_error   # non-None when SMTP failed and fell back to manual


def send_or_generate_reminder(
    session: Session,
    invoice_id: str,
    level: int,
    fee_ore: int,
    sent_by: str = "user",
    triggered_by: str = "manual",
) -> ReminderResult:
    """Create and optionally email a reminder for invoice_id at the given level.

    - Validates invoice exists, is in 'sent' status, and level 1-3.
    - Refuses if a reminder at this level already exists for this invoice.
    - Generates reminder text.
    - Tries SMTP if configured; on failure records method='failed' with error,
      still saves the record so the text is available for manual sending.
    - Returns ReminderResult.
    """
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise ValueError(f"Faktura '{invoice_id}' ikke fundet")
    if invoice.status not in (InvoiceStatus.sent,):
        raise ValueError(
            f"Rykker kan kun sendes på fakturaer med status 'sent' "
            f"(nuværende status: '{invoice.status.value}')"
        )
    if level not in (1, 2, 3):
        raise ValueError("Niveau skal være 1, 2 eller 3")

    existing = session.exec(
        select(InvoiceReminder).where(
            InvoiceReminder.invoice_id == invoice_id,
            InvoiceReminder.level == level,
        )
    ).first()
    if existing:
        raise ValueError(
            f"{_LEVEL_LABELS[level]} er allerede sendt for denne faktura "
            f"(oprettet {existing.created_at.strftime('%d-%m-%Y')})"
        )

    customer = session.get(Customer, invoice.customer_id)
    if not customer:
        raise ValueError("Kunde ikke fundet for denne faktura")

    company = session.get(Company, invoice.company_id)
    if not company:
        raise ValueError("Virksomhed ikke fundet")

    subject, body = generate_reminder(invoice, customer, company, level, fee_ore)

    method = "manual"
    smtp_error: Optional[str] = None
    email_to: Optional[str] = customer.email

    email_cfg = resolve_email_config(session, invoice.company_id)
    if email_cfg is not None and email_to:
        try:
            send_email(to=email_to, subject=subject, body=body, cfg=email_cfg)
            method = "email"
        except (SmtpNotConfiguredError, SmtpSendError) as e:
            method = "failed"
            smtp_error = str(e)

    reminder = InvoiceReminder(
        invoice_id=invoice_id,
        company_id=invoice.company_id,
        customer_id=invoice.customer_id,
        level=level,
        fee_ore=fee_ore,
        method=method,
        email_to=email_to if method == "email" else None,
        subject=subject,
        body_text=body,
        error_detail=smtp_error,
        sent_by=sent_by,
        triggered_by=triggered_by,
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)

    return ReminderResult(reminder=reminder, method=method, smtp_error=smtp_error)


# ── Automatic batch job ───────────────────────────────────────────────────────

# Reminder thresholds: (min_days_overdue, level, fee_ore, queue_only)
# queue_only=True means create with method='manual' and do NOT send via SMTP.
_AUTO_THRESHOLDS = [
    (timedelta(days=7),  1, REMINDER_FEE_ORE_1, False),
    (timedelta(days=14), 2, REMINDER_FEE_ORE_2, False),
    (timedelta(days=21), 3, REMINDER_FEE_ORE_3, True),
]


def run_automatic_reminders(session: Session, company_id: str, today: date) -> dict:
    """Find overdue invoices and create / send reminders automatically.

    Thresholds (days past due_date):
      +7d  → level 1 (fee=REMINDER_FEE_ORE_1, auto-sent via send_or_generate_reminder)
      +14d → level 2 (fee=REMINDER_FEE_ORE_2, auto-sent via send_or_generate_reminder)
      +21d → level 3 (fee=REMINDER_FEE_ORE_3, method='manual' — NOT auto-sent, queued)

    Idempotency: the (invoice_id, level) dedup check inside send_or_generate_reminder
    prevents duplicate DB records on re-run.

    # NOTE: RISK-03 crash window — for levels 1/2, SMTP send precedes DB commit inside
    # send_or_generate_reminder. If the process crashes between send and commit, the
    # reminder email may be re-sent on the next run. This is bounded by the per-level
    # dedup guard which prevents double DB records once the commit succeeds.
    # Pay-down trigger: add a two-phase send-state column if duplicate sends are observed.

    Errors on individual invoices are collected and returned; processing continues
    for remaining invoices (batch job Iron Law exception — documented inline).
    """
    processed = 0
    sent = 0
    queued = 0
    errors: list[str] = []

    overdue = session.exec(
        select(Invoice).where(
            Invoice.company_id == company_id,
            Invoice.status == InvoiceStatus.sent,
            Invoice.active.is_(True),
            Invoice.due_date.isnot(None),
            Invoice.due_date < today,
        )
    ).all()

    for invoice in overdue:
        days_overdue = (today - invoice.due_date).days
        for min_delta, level, fee_ore, queue_only in _AUTO_THRESHOLDS:
            if days_overdue < min_delta.days:
                continue
            # Check dedup before attempting — avoids a ValueError round-trip
            already_exists = session.exec(
                select(InvoiceReminder).where(
                    InvoiceReminder.invoice_id == invoice.id,
                    InvoiceReminder.level == level,
                )
            ).first()
            if already_exists:
                continue
            # A failure on one invoice must not abort the rest of the batch.
            # This is the documented exception to Iron Law 2 for batch processing:
            # errors are surfaced in the returned dict, not silently dropped.
            try:
                if queue_only:
                    # Level 3: create manually-reviewed reminder; do NOT trigger SMTP.
                    reminder = InvoiceReminder(
                        id=str(uuid.uuid4()),
                        invoice_id=invoice.id,
                        company_id=company_id,
                        customer_id=invoice.customer_id,
                        level=level,
                        fee_ore=fee_ore,
                        method="manual",
                        subject=f"Rykker nr. {level}",
                        body_text="Afventer manuel behandling.",
                        sent_by="scheduler",
                        triggered_by="auto",
                    )
                    session.add(reminder)
                    session.commit()
                    processed += 1
                    queued += 1
                else:
                    result = send_or_generate_reminder(
                        session=session,
                        invoice_id=invoice.id,
                        level=level,
                        fee_ore=fee_ore,
                        sent_by="scheduler",
                        triggered_by="auto",
                    )
                    processed += 1
                    if result.method == "email":
                        sent += 1
                    else:
                        # SMTP not configured or failed — reminder saved as
                        # method='manual'/'failed' and queued for manual dispatch.
                        queued += 1
            except Exception as exc:  # batch: collect errors, continue remaining invoices
                errors.append(f"Faktura {invoice.id} niveau {level}: {exc!s}")

    return {"processed": processed, "sent": sent, "queued_for_review": queued, "errors": errors}
