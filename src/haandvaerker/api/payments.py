import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.invoice import Invoice, InvoiceStatus
from ..models.payment import Payment, PaymentCreate, PaymentRead, PaymentSummary
from ..utils import to_decimal

router = APIRouter(prefix="/payments", tags=["payments"])



def _require_payable_invoice(invoice_id: str, session: Session) -> Invoice:
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=422, detail=f"Invoice '{invoice_id}' not found")
    if not invoice.active:
        raise HTTPException(status_code=422, detail=f"Invoice '{invoice_id}' is inactive")
    if invoice.status == InvoiceStatus.cancelled:
        raise HTTPException(status_code=422, detail="Cannot pay a cancelled invoice")
    return invoice


def _sum_active_payments(invoice_id: str, session: Session) -> Decimal:
    rows = session.exec(
        select(Payment)
        .where(Payment.invoice_id == invoice_id)
        .where(Payment.active == True)  # noqa: E712
    ).all()
    return sum((to_decimal(p.amount) for p in rows), Decimal("0"))


# /summary must be registered before /{payment_id}
@router.get("/summary", response_model=PaymentSummary)
def get_summary(invoice_id: str, ctx: CompanyContextDep) -> PaymentSummary:
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=422, detail=f"Invoice '{invoice_id}' not found")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    q = Decimal("0.01")
    total_paid = _sum_active_payments(invoice_id, session).quantize(q, ROUND_HALF_UP)
    invoice_total = to_decimal(invoice.total).quantize(q, ROUND_HALF_UP)
    outstanding = max(Decimal("0"), invoice_total - total_paid).quantize(q, ROUND_HALF_UP)
    overpaid = max(Decimal("0"), total_paid - invoice_total).quantize(q, ROUND_HALF_UP)
    return PaymentSummary(
        invoice_id=invoice_id,
        invoice_total=float(invoice_total),
        total_paid=float(total_paid),
        outstanding=float(outstanding),
        overpaid=float(overpaid),
    )


@router.post("/", response_model=PaymentRead, status_code=201)
def create_payment(data: PaymentCreate, ctx: CompanyContextDep) -> PaymentRead:
    session = ctx.session
    invoice = _require_payable_invoice(data.invoice_id, session)
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    payment_id = data.id or str(uuid.uuid4())
    if session.get(Payment, payment_id):
        raise HTTPException(status_code=409, detail=f"Payment {payment_id} already exists")

    payment = Payment(
        id=payment_id,
        invoice_id=invoice.id,
        company_id=invoice.company_id,
        project_id=invoice.project_id,
        amount=data.amount,
        payment_date=data.payment_date,
        method=data.method,
        notes=data.notes,
    )
    session.add(payment)
    session.flush()

    if invoice.status == InvoiceStatus.sent:
        total_paid = _sum_active_payments(invoice.id, session)
        if total_paid >= to_decimal(invoice.total):
            invoice.status = InvoiceStatus.paid
            session.add(invoice)

    session.commit()
    session.refresh(payment)
    return PaymentRead.model_validate(payment)


@router.get("/", response_model=list[PaymentRead])
def list_payments(
    ctx: CompanyContextDep,
    active_only: bool = True,
    invoice_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> list[PaymentRead]:
    session = ctx.session
    query = select(Payment).where(Payment.company_id == ctx.company_id)
    if active_only:
        query = query.where(Payment.active == True)  # noqa: E712
    if invoice_id is not None:
        query = query.where(Payment.invoice_id == invoice_id)
    if project_id is not None:
        query = query.where(Payment.project_id == project_id)
    return [PaymentRead.model_validate(p) for p in session.exec(query).all()]


@router.get("/{payment_id}", response_model=PaymentRead)
def get_payment(payment_id: str, ctx: CompanyContextDep) -> PaymentRead:
    session = ctx.session
    payment = session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return PaymentRead.model_validate(payment)


@router.delete("/{payment_id}", status_code=204)
def deactivate_payment(payment_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    payment = session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    payment.active = False
    session.add(payment)
    session.commit()
