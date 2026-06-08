import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.company import Company
from ..models.customer import Customer
from ..models.project import Project
from ..models.expense import Expense
from ..models.invoice import (
    Invoice, InvoiceCreate, InvoiceDraftFromProject, InvoiceLine, InvoiceLineCreate,
    InvoiceLineRead, InvoiceRead, InvoiceSequence, InvoiceStatus, InvoiceSummary,
    InvoiceUpdate, compute_line_total, compute_invoice_totals,
)
from ..models.time_entry import TimeEntry
from ..pdf.invoice_pdf import generate_invoice_pdf
from ..utils import to_decimal

router = APIRouter(prefix="/invoices", tags=["invoices"])


VALID_TRANSITIONS: dict[InvoiceStatus, set[InvoiceStatus]] = {
    InvoiceStatus.draft: {InvoiceStatus.sent, InvoiceStatus.cancelled},
    InvoiceStatus.sent: {InvoiceStatus.paid, InvoiceStatus.cancelled},
}


def _require_active_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' not found")
    if not project.active:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' is inactive")
    return project


def _next_invoice_number(session: Session) -> str:
    year = date.today().year
    seq = session.get(InvoiceSequence, year)
    if seq is None:
        seq = InvoiceSequence(year=year, last_number=0)
    seq.last_number += 1
    session.add(seq)
    return f"FKT-{year}-{seq.last_number:03d}"


def _build_lines(
    invoice_id: str, line_creates: list[InvoiceLineCreate], session: Session
) -> list[InvoiceLine]:
    lines = []
    for lc in line_creates:
        lt = compute_line_total(lc.quantity, lc.unit_price)
        line = InvoiceLine(
            id=str(uuid.uuid4()),
            invoice_id=invoice_id,
            line_total=lt,
            **lc.model_dump(),
        )
        session.add(line)
        lines.append(line)
    return lines


def _build_invoice_read(invoice: Invoice, session: Session) -> InvoiceRead:
    lines = session.exec(
        select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
    ).all()
    line_reads = [InvoiceLineRead.model_validate(ln) for ln in lines]
    return InvoiceRead(**{**invoice.model_dump(), "lines": line_reads})


def _apply_transition(invoice: Invoice, target: InvoiceStatus, session: Session) -> InvoiceRead:
    allowed = VALID_TRANSITIONS.get(invoice.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{invoice.status}' to '{target}'",
        )
    invoice.status = target
    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return _build_invoice_read(invoice, session)


# Fixed paths must be registered before /{invoice_id} to avoid routing conflicts
@router.post("/draft-from-project", response_model=InvoiceRead, status_code=201)
def draft_invoice_from_project(data: InvoiceDraftFromProject, ctx: CompanyContextDep) -> InvoiceRead:
    session = ctx.session
    project = _require_active_project(data.project_id, session)
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if data.due_date < data.issue_date:
        raise HTTPException(status_code=422, detail="due_date must be >= issue_date")

    unbilled_entries = session.exec(
        select(TimeEntry)
        .where(TimeEntry.project_id == data.project_id)
        .where(TimeEntry.active == True)  # noqa: E712
        .where(TimeEntry.billable == True)  # noqa: E712
        .where(TimeEntry.invoice_id == None)  # noqa: E711
    ).all()

    unbilled_expenses = session.exec(
        select(Expense)
        .where(Expense.project_id == data.project_id)
        .where(Expense.active == True)  # noqa: E712
        .where(Expense.billable == True)  # noqa: E712
        .where(Expense.invoice_id == None)  # noqa: E711
    ).all()

    if not unbilled_entries and not unbilled_expenses:
        raise HTTPException(status_code=422, detail="No unbilled billable records for this project")

    invoice_id = str(uuid.uuid4())
    invoice_number = _next_invoice_number(session)
    title = data.title or f"Faktura – {project.title}"

    line_creates: list[InvoiceLineCreate] = []
    for entry in unbilled_entries:
        desc = entry.description or "Arbejdsløn"
        line_creates.append(InvoiceLineCreate(
            description=desc,
            unit="timer",
            quantity=entry.hours,
            unit_price=entry.hourly_rate,
        ))
    for expense in unbilled_expenses:
        desc = expense.description or expense.category.value
        line_creates.append(InvoiceLineCreate(
            description=desc,
            unit=None,
            quantity=1.0,
            unit_price=expense.amount_excl_vat,
        ))

    lines = _build_lines(invoice_id, line_creates, session)
    subtotal, vat_amount, total = compute_invoice_totals([ln.line_total for ln in lines])

    invoice = Invoice(
        id=invoice_id,
        company_id=ctx.company_id,
        project_id=data.project_id,
        customer_id=project.customer_id,
        invoice_number=invoice_number,
        title=title,
        issue_date=data.issue_date,
        due_date=data.due_date,
        subtotal=subtotal,
        vat_amount=vat_amount,
        total=total,
    )
    session.add(invoice)
    session.flush()

    for entry in unbilled_entries:
        entry.invoice_id = invoice_id
        session.add(entry)
    for expense in unbilled_expenses:
        expense.invoice_id = invoice_id
        session.add(expense)

    session.commit()
    session.refresh(invoice)
    return _build_invoice_read(invoice, session)


@router.get("/summary", response_model=InvoiceSummary)
def get_summary(project_id: str, ctx: CompanyContextDep) -> InvoiceSummary:
    session = ctx.session
    project = _require_active_project(project_id, session)
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    entries = session.exec(
        select(Invoice)
        .where(Invoice.project_id == project_id)
        .where(Invoice.active == True)  # noqa: E712
        .where(Invoice.status != InvoiceStatus.cancelled)
    ).all()

    q = Decimal("0.01")
    zero = Decimal("0")
    total_invoiced = float(
        sum((to_decimal(e.total) for e in entries), zero).quantize(q, ROUND_HALF_UP)
    )
    total_paid = float(
        sum(
            (to_decimal(e.total) for e in entries if e.status == InvoiceStatus.paid),
            zero,
        ).quantize(q, ROUND_HALF_UP)
    )
    outstanding = float(
        sum(
            (to_decimal(e.total) for e in entries if e.status == InvoiceStatus.sent),
            zero,
        ).quantize(q, ROUND_HALF_UP)
    )
    return InvoiceSummary(
        project_id=project_id,
        total_invoiced=total_invoiced,
        total_paid=total_paid,
        outstanding=outstanding,
    )


@router.post("/", response_model=InvoiceRead, status_code=201)
def create_invoice(data: InvoiceCreate, ctx: CompanyContextDep) -> InvoiceRead:
    session = ctx.session
    project = _require_active_project(data.project_id, session)
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if data.due_date < data.issue_date:
        raise HTTPException(status_code=422, detail="due_date must be >= issue_date")

    invoice_id = data.id or str(uuid.uuid4())
    if session.get(Invoice, invoice_id):
        raise HTTPException(status_code=409, detail=f"Invoice {invoice_id} already exists")
    invoice_number = _next_invoice_number(session)

    lines = _build_lines(invoice_id, data.lines, session)
    subtotal, vat_amount, total = compute_invoice_totals([ln.line_total for ln in lines])

    invoice = Invoice(
        id=invoice_id,
        company_id=ctx.company_id,
        project_id=data.project_id,
        customer_id=project.customer_id,
        invoice_number=invoice_number,
        title=data.title,
        description=data.description,
        issue_date=data.issue_date,
        due_date=data.due_date,
        notes=data.notes,
        subtotal=subtotal,
        vat_amount=vat_amount,
        total=total,
    )
    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return _build_invoice_read(invoice, session)


@router.get("/", response_model=list[InvoiceRead])
def list_invoices(
    ctx: CompanyContextDep,
    active_only: bool = True,
    project_id: Optional[str] = None,
    status: Optional[InvoiceStatus] = None,
) -> list[InvoiceRead]:
    session = ctx.session
    query = select(Invoice).where(Invoice.company_id == ctx.company_id)
    if active_only:
        query = query.where(Invoice.active == True)  # noqa: E712
    if project_id is not None:
        query = query.where(Invoice.project_id == project_id)
    if status is not None:
        query = query.where(Invoice.status == status)
    return [_build_invoice_read(inv, session) for inv in session.exec(query).all()]


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(invoice_id: str, ctx: CompanyContextDep) -> Response:
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    project = session.get(Project, invoice.project_id)
    company = session.get(Company, invoice.company_id) if project else None
    customer = session.get(Customer, invoice.customer_id) if invoice.customer_id else None
    lines = session.exec(
        select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id)
    ).all()

    cvr_raw = company.cvr_number if company else None
    cvr_masked = f"****{cvr_raw[-4:]}" if cvr_raw and len(cvr_raw) >= 4 else None
    pdf_bytes = generate_invoice_pdf(
        invoice_number=invoice.invoice_number,
        title=invoice.title,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        notes=invoice.notes,
        company_name=company.name if company else "—",
        company_address=company.address if company else None,
        company_cvr_masked=cvr_masked,
        customer_name=customer.name if customer else "—",
        customer_address=customer.address if customer else None,
        subtotal=invoice.subtotal,
        vat_amount=invoice.vat_amount,
        total=invoice.total,
        lines=[
            {
                "description": ln.description,
                "unit": ln.unit,
                "quantity": ln.quantity,
                "unit_price": ln.unit_price,
                "line_total": ln.line_total,
            }
            for ln in lines
        ],
    )
    filename = f"{invoice.invoice_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(invoice_id: str, ctx: CompanyContextDep) -> InvoiceRead:
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _build_invoice_read(invoice, session)


@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(invoice_id: str, data: InvoiceUpdate, ctx: CompanyContextDep) -> InvoiceRead:
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if invoice.status != InvoiceStatus.draft:
        raise HTTPException(status_code=409, detail="Can only edit draft invoices")

    for field, value in data.model_dump(exclude_unset=True, exclude={"lines"}).items():
        setattr(invoice, field, value)

    # Validate dates if both are now set
    issue = invoice.issue_date
    due = invoice.due_date
    if due < issue:
        raise HTTPException(status_code=422, detail="due_date must be >= issue_date")

    if data.lines is not None:
        for old in session.exec(
            select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id)
        ).all():
            session.delete(old)
        session.flush()
        new_lines = _build_lines(invoice_id, data.lines, session)
        invoice.subtotal, invoice.vat_amount, invoice.total = compute_invoice_totals(
            [ln.line_total for ln in new_lines]
        )

    session.add(invoice)
    session.commit()
    session.refresh(invoice)
    return _build_invoice_read(invoice, session)


@router.delete("/{invoice_id}", status_code=204)
def deactivate_invoice(invoice_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    invoice.active = False
    session.add(invoice)
    session.commit()


@router.post("/{invoice_id}/send", response_model=InvoiceRead)
def send_invoice(invoice_id: str, ctx: CompanyContextDep) -> InvoiceRead:
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(invoice, InvoiceStatus.sent, session)


@router.post("/{invoice_id}/pay", response_model=InvoiceRead)
def pay_invoice(invoice_id: str, ctx: CompanyContextDep) -> InvoiceRead:
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(invoice, InvoiceStatus.paid, session)


@router.post("/{invoice_id}/cancel", response_model=InvoiceRead)
def cancel_invoice(invoice_id: str, ctx: CompanyContextDep) -> InvoiceRead:
    session = ctx.session
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(invoice, InvoiceStatus.cancelled, session)
