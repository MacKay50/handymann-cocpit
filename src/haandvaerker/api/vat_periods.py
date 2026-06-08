import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.expense import Expense
from ..models.invoice import Invoice, InvoiceStatus
from ..models.vat_period import (
    VatExport, VatExportExpenseItem, VatExportInvoiceItem,
    VatPeriod, VatPeriodCreate, VatPeriodRead, VatPeriodStatus, VatPreview,
)
from ..utils import to_decimal

router = APIRouter(prefix="/vat-periods", tags=["vat-periods"])


VALID_TRANSITIONS: dict[VatPeriodStatus, set[VatPeriodStatus]] = {
    VatPeriodStatus.open: {VatPeriodStatus.locked},
    VatPeriodStatus.locked: {VatPeriodStatus.submitted, VatPeriodStatus.open},
}


def _calc_vat(
    company_id: str, period_start: date, period_end: date, session: Session
) -> tuple[float, float, int, int]:
    """Returns (outgoing_vat, incoming_vat, invoice_count, expense_count)."""
    q = Decimal("0.01")
    zero = Decimal("0")

    invoices = session.exec(
        select(Invoice)
        .where(Invoice.company_id == company_id)
        .where(Invoice.active == True)  # noqa: E712
        .where(Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.paid]))
        .where(Invoice.issue_date >= period_start)
        .where(Invoice.issue_date <= period_end)
    ).all()

    expenses = session.exec(
        select(Expense)
        .where(Expense.company_id == company_id)
        .where(Expense.active == True)  # noqa: E712
        .where(Expense.date >= period_start)
        .where(Expense.date <= period_end)
    ).all()

    outgoing = float(
        sum((to_decimal(i.vat_amount) for i in invoices), zero).quantize(q, ROUND_HALF_UP)
    )
    incoming = float(
        sum((to_decimal(e.vat_amount) for e in expenses), zero).quantize(q, ROUND_HALF_UP)
    )
    return outgoing, incoming, len(invoices), len(expenses)


# /preview and /export/{id} must be registered before /{id}
@router.get("/preview", response_model=VatPreview)
def preview_vat(
    ctx: CompanyContextDep,
    period_start: date,
    period_end: date,
) -> VatPreview:
    session = ctx.session
    outgoing, incoming, inv_count, exp_count = _calc_vat(
        ctx.company_id, period_start, period_end, session
    )
    q = Decimal("0.01")
    net = float(
        (to_decimal(outgoing) - to_decimal(incoming)).quantize(q, ROUND_HALF_UP)
    )
    return VatPreview(
        company_id=ctx.company_id,
        period_start=period_start,
        period_end=period_end,
        outgoing_vat=outgoing,
        incoming_vat=incoming,
        net_vat=net,
        invoice_count=inv_count,
        expense_count=exp_count,
    )


@router.post("/", response_model=VatPeriodRead, status_code=201)
def create_vat_period(data: VatPeriodCreate, ctx: CompanyContextDep) -> VatPeriodRead:
    session = ctx.session
    if data.period_end < data.period_start:
        raise HTTPException(status_code=422, detail="period_end must be >= period_start")

    period_id = data.id or str(uuid.uuid4())
    if session.get(VatPeriod, period_id):
        raise HTTPException(status_code=409, detail=f"VatPeriod {period_id} already exists")

    overlap = session.exec(
        select(VatPeriod)
        .where(VatPeriod.company_id == ctx.company_id)
        .where(VatPeriod.active == True)  # noqa: E712
        .where(VatPeriod.period_start <= data.period_end)
        .where(VatPeriod.period_end >= data.period_start)
    ).first()
    if overlap:
        raise HTTPException(status_code=409, detail="An overlapping VAT period already exists")

    period = VatPeriod(
        id=period_id,
        company_id=ctx.company_id,
        period_start=data.period_start,
        period_end=data.period_end,
        notes=data.notes,
    )
    session.add(period)
    session.commit()
    session.refresh(period)
    return VatPeriodRead.model_validate(period)


@router.get("/", response_model=list[VatPeriodRead])
def list_vat_periods(
    ctx: CompanyContextDep,
    active_only: bool = True,
    status: Optional[VatPeriodStatus] = None,
) -> list[VatPeriodRead]:
    session = ctx.session
    query = select(VatPeriod).where(VatPeriod.company_id == ctx.company_id)
    if active_only:
        query = query.where(VatPeriod.active == True)  # noqa: E712
    if status is not None:
        query = query.where(VatPeriod.status == status)
    return [VatPeriodRead.model_validate(p) for p in session.exec(query).all()]


@router.get("/{period_id}/export", response_model=VatExport)
def export_vat_period(period_id: str, ctx: CompanyContextDep) -> VatExport:
    session = ctx.session
    period = session.get(VatPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="VatPeriod not found")
    if period.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if period.status == VatPeriodStatus.open:
        raise HTTPException(status_code=409, detail="Lock the period before exporting")

    invoices = session.exec(
        select(Invoice)
        .where(Invoice.company_id == period.company_id)
        .where(Invoice.active == True)  # noqa: E712
        .where(Invoice.status.in_([InvoiceStatus.sent, InvoiceStatus.paid]))
        .where(Invoice.issue_date >= period.period_start)
        .where(Invoice.issue_date <= period.period_end)
    ).all()

    expenses = session.exec(
        select(Expense)
        .where(Expense.company_id == period.company_id)
        .where(Expense.active == True)  # noqa: E712
        .where(Expense.date >= period.period_start)
        .where(Expense.date <= period.period_end)
    ).all()

    return VatExport(
        period_id=period.id,
        company_id=period.company_id,
        period_start=period.period_start,
        period_end=period.period_end,
        status=period.status,
        outgoing_vat=period.outgoing_vat or 0.0,
        incoming_vat=period.incoming_vat or 0.0,
        net_vat=period.net_vat or 0.0,
        invoice_count=period.invoice_count or 0,
        expense_count=period.expense_count or 0,
        invoices=[
            VatExportInvoiceItem(
                id=inv.id,
                invoice_number=inv.invoice_number,
                issue_date=inv.issue_date,
                customer_id=inv.customer_id,
                subtotal=inv.subtotal,
                vat_amount=inv.vat_amount,
                total=inv.total,
                status=inv.status,
            )
            for inv in invoices
        ],
        expenses=[
            VatExportExpenseItem(
                id=exp.id,
                date=exp.date,
                category=exp.category,
                description=exp.description,
                amount_excl_vat=exp.amount_excl_vat,
                vat_amount=exp.vat_amount,
                amount_total=exp.amount_total,
            )
            for exp in expenses
        ],
    )


@router.get("/{period_id}", response_model=VatPeriodRead)
def get_vat_period(period_id: str, ctx: CompanyContextDep) -> VatPeriodRead:
    session = ctx.session
    period = session.get(VatPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="VatPeriod not found")
    if period.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return VatPeriodRead.model_validate(period)


@router.post("/{period_id}/lock", response_model=VatPeriodRead)
def lock_vat_period(period_id: str, ctx: CompanyContextDep) -> VatPeriodRead:
    session = ctx.session
    period = session.get(VatPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="VatPeriod not found")
    if period.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    allowed = VALID_TRANSITIONS.get(period.status, set())
    if VatPeriodStatus.locked not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot lock a period with status '{period.status}'",
        )
    outgoing, incoming, inv_count, exp_count = _calc_vat(
        period.company_id, period.period_start, period.period_end, session
    )
    q = Decimal("0.01")
    net = float(
        (to_decimal(outgoing) - to_decimal(incoming)).quantize(q, ROUND_HALF_UP)
    )
    period.status = VatPeriodStatus.locked
    period.outgoing_vat = outgoing
    period.incoming_vat = incoming
    period.net_vat = net
    period.invoice_count = inv_count
    period.expense_count = exp_count
    session.add(period)
    session.commit()
    session.refresh(period)
    return VatPeriodRead.model_validate(period)


@router.post("/{period_id}/reopen", response_model=VatPeriodRead)
def reopen_vat_period(period_id: str, ctx: CompanyContextDep) -> VatPeriodRead:
    session = ctx.session
    period = session.get(VatPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="VatPeriod not found")
    if period.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    allowed = VALID_TRANSITIONS.get(period.status, set())
    if VatPeriodStatus.open not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reopen a period with status '{period.status}'",
        )
    period.status = VatPeriodStatus.open
    period.outgoing_vat = None
    period.incoming_vat = None
    period.net_vat = None
    period.invoice_count = None
    period.expense_count = None
    session.add(period)
    session.commit()
    session.refresh(period)
    return VatPeriodRead.model_validate(period)


@router.post("/{period_id}/submit", response_model=VatPeriodRead)
def submit_vat_period(period_id: str, ctx: CompanyContextDep) -> VatPeriodRead:
    session = ctx.session
    period = session.get(VatPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="VatPeriod not found")
    if period.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    allowed = VALID_TRANSITIONS.get(period.status, set())
    if VatPeriodStatus.submitted not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot submit a period with status '{period.status}'",
        )
    period.status = VatPeriodStatus.submitted
    session.add(period)
    session.commit()
    session.refresh(period)
    return VatPeriodRead.model_validate(period)


@router.delete("/{period_id}", status_code=204)
def delete_vat_period(period_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    period = session.get(VatPeriod, period_id)
    if not period:
        raise HTTPException(status_code=404, detail="VatPeriod not found")
    if period.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if period.status != VatPeriodStatus.open:
        raise HTTPException(
            status_code=409,
            detail="Can only delete open periods",
        )
    period.active = False
    session.add(period)
    session.commit()
