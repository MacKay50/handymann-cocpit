from __future__ import annotations

import pathlib
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import func, select

from ..dependencies import CompanyContextDep
from ..models.bank_transaction import BankTransaction, BankTransactionStatus
from ..models.customer import Customer
from ..models.economic_customer import EconomicCustomer
from ..models.economic_invoice import EconomicInvoice, EconomicInvoiceRead, EconomicInvoiceStatus
from ..models.invoice import Invoice
from ..models.project import Project, ProjectStatus
from ..models.reconciliation_match import ReconciliationMatch
from ..services.danish_csv import (
    ImportResult,
    decode_csv_bytes,
    parse_economic_invoice_csv,
    parse_economic_invoice_xlsx,
)

router = APIRouter(prefix="/economic-invoices", tags=["economic-invoices"])


def _to_read(obj: EconomicInvoice) -> EconomicInvoiceRead:
    """Convert EconomicInvoice ORM object to EconomicInvoiceRead.

    is_overdue is computed at read time (RISK-05: not stored in the database).
    """
    today = date.today()
    is_overdue = obj.status == EconomicInvoiceStatus.unmatched and obj.due_date < today
    return EconomicInvoiceRead(
        id=obj.id,
        company_id=obj.company_id,
        economic_invoice_number=obj.economic_invoice_number,
        customer_name=obj.customer_name,
        net_amount_ore=obj.net_amount_ore,
        vat_amount_ore=obj.vat_amount_ore,
        gross_amount_ore=obj.gross_amount_ore,
        invoice_date=obj.invoice_date,
        due_date=obj.due_date,
        payment_date=obj.payment_date,
        status=obj.status,
        linked_project_id=obj.linked_project_id,
        economic_customer_id=obj.economic_customer_id,
        invoice_id=obj.invoice_id,
        imported_at=obj.imported_at,
        active=obj.active,
        is_overdue=is_overdue,
    )


@router.post("/import", response_model=ImportResult, status_code=201)
def import_economic_invoices(
    file_path: str,
    ctx: CompanyContextDep,
) -> ImportResult:
    """Import e-conomic invoice CSV. All-or-nothing: if any row fails validation, 422 with error list."""
    session = ctx.session
    company_id = ctx.company_id

    p = pathlib.Path(file_path)
    if not p.exists():
        raise HTTPException(status_code=422, detail=f"Fil ikke fundet: {file_path}")
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if p.suffix.lower() == ".xlsx":
        rows, errors = parse_economic_invoice_xlsx(raw, company_id)
    else:
        try:
            content = decode_csv_bytes(raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        rows, errors = parse_economic_invoice_csv(content, company_id)

    if errors:
        raise HTTPException(status_code=422, detail=errors)

    for row in rows:
        invoice = EconomicInvoice(**row.model_dump())
        session.add(invoice)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Import indeholder allerede importerede fakturanumre — ingen rækker er gemt. Kontroller om disse fakturaer er importeret tidligere.",
        )

    return ImportResult(rows_imported=len(rows), rows_skipped=0, errors=[])


@router.post("/import-upload", response_model=ImportResult, status_code=201)
async def import_economic_invoices_upload(
    ctx: CompanyContextDep,
    file: UploadFile = File(...),
) -> ImportResult:
    """Import e-conomic invoice CSV via browser file upload. All-or-nothing."""
    session = ctx.session
    company_id = ctx.company_id
    raw = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".xlsx"):
        rows, errors = parse_economic_invoice_xlsx(raw, company_id)
    else:
        try:
            content = decode_csv_bytes(raw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        rows, errors = parse_economic_invoice_csv(content, company_id)

    if errors:
        raise HTTPException(status_code=422, detail=errors)
    for row in rows:
        invoice = EconomicInvoice(**row.model_dump())
        session.add(invoice)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Import indeholder allerede importerede fakturanumre — ingen rækker er gemt.",
        )
    return ImportResult(rows_imported=len(rows), rows_skipped=0, errors=[])


@router.get("/", response_model=list[EconomicInvoiceRead])
def list_economic_invoices(
    ctx: CompanyContextDep,
    status: Optional[EconomicInvoiceStatus] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    active_only: bool = True,
) -> list[EconomicInvoiceRead]:
    """List e-conomic invoices for the session company with optional filters.

    is_overdue is computed at read time — not stored (RISK-05).
    """
    session = ctx.session
    q = select(EconomicInvoice).where(EconomicInvoice.company_id == ctx.company_id)
    if active_only:
        q = q.where(EconomicInvoice.active == True)  # noqa: E712
    if status:
        q = q.where(EconomicInvoice.status == status)
    if date_from:
        q = q.where(EconomicInvoice.invoice_date >= date_from)
    if date_to:
        q = q.where(EconomicInvoice.invoice_date <= date_to)
    return [_to_read(inv) for inv in session.exec(q).all()]


class LinkInvoiceRequest(BaseModel):
    invoice_id: Optional[str] = None  # null to clear the link


@router.patch("/{economic_invoice_id}/link-invoice", response_model=EconomicInvoiceRead)
def link_invoice(
    economic_invoice_id: str,
    data: LinkInvoiceRequest,
    ctx: CompanyContextDep,
) -> EconomicInvoiceRead:
    """Manually link an EconomicInvoice to an internal Invoice (CONT-10).

    Pass invoice_id=null to clear the link.
    NOTE: SQLite FK enforcement is off — app-level validation guards cross-company writes (RISK-08).
    """
    session = ctx.session
    ec_inv = session.get(EconomicInvoice, economic_invoice_id)
    if not ec_inv or not ec_inv.active:
        raise HTTPException(status_code=404, detail="E-conomic faktura ikke fundet.")
    if ec_inv.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if data.invoice_id is not None:
        invoice = session.get(Invoice, data.invoice_id)
        if not invoice or not invoice.active:
            raise HTTPException(status_code=404, detail=f"Faktura '{data.invoice_id}' ikke fundet.")
        if invoice.company_id != ctx.company_id:
            raise HTTPException(status_code=422, detail="Fakturaen tilhører ikke denne virksomhed.")

    ec_inv.invoice_id = data.invoice_id
    session.add(ec_inv)
    session.commit()
    session.refresh(ec_inv)
    return _to_read(ec_inv)


class DeriveCustomersResult(BaseModel):
    created: int
    linked: int
    already_linked: int


class HistoricalProjectsResult(BaseModel):
    created: int
    skipped: list[str]


@router.post("/derive-customers", response_model=DeriveCustomersResult, status_code=200)
def derive_customers(ctx: CompanyContextDep) -> DeriveCustomersResult:
    """Extract unique debitor names from invoices → create EconomicCustomer stubs (source=derived).

    Invoices are linked to the EconomicCustomer stub by normalised name.
    Already-linked invoices are counted but not re-processed.
    """
    session = ctx.session
    company_id = ctx.company_id

    invoices = session.exec(
        select(EconomicInvoice).where(
            EconomicInvoice.company_id == company_id,
            EconomicInvoice.active.is_(True),
        )
    ).all()

    already_linked = sum(1 for inv in invoices if inv.economic_customer_id is not None)
    unlinked = [inv for inv in invoices if inv.economic_customer_id is None]

    name_groups: dict[str, list[EconomicInvoice]] = {}
    for inv in unlinked:
        key = inv.customer_name.strip().lower()
        name_groups.setdefault(key, []).append(inv)

    created = 0
    linked = 0

    for norm_name, group_invoices in name_groups.items():
        canonical_name = group_invoices[0].customer_name.strip()

        existing_ec = session.exec(
            select(EconomicCustomer).where(
                EconomicCustomer.company_id == company_id,
                func.lower(EconomicCustomer.name) == norm_name,
                EconomicCustomer.active.is_(True),
            )
        ).first()

        if existing_ec is None:
            ec_number = f"DRV-{str(uuid.uuid4())[:8].upper()}"
            existing_ec = EconomicCustomer(
                company_id=company_id,
                economic_customer_number=ec_number,
                name=canonical_name,
                source="derived",
            )
            session.add(existing_ec)
            session.flush()
            created += 1

        for inv in group_invoices:
            inv.economic_customer_id = existing_ec.id
            session.add(inv)
            linked += 1

    session.commit()
    return DeriveCustomersResult(created=created, linked=linked, already_linked=already_linked)


@router.post("/create-historical-projects", response_model=HistoricalProjectsResult, status_code=201)
def create_historical_projects(ctx: CompanyContextDep) -> HistoricalProjectsResult:
    """For each bank-matched invoice with an EconomicCustomer link: create a completed Project."""
    session = ctx.session
    company_id = ctx.company_id

    matched_invoices = session.exec(
        select(EconomicInvoice).where(
            EconomicInvoice.company_id == company_id,
            EconomicInvoice.status == EconomicInvoiceStatus.matched,
            EconomicInvoice.economic_customer_id.is_not(None),
            EconomicInvoice.linked_project_id.is_(None),
            EconomicInvoice.active.is_(True),
        )
    ).all()

    created = 0
    skipped: list[str] = []

    for inv in matched_invoices:
        ec = session.get(EconomicCustomer, inv.economic_customer_id)
        if ec is None or not ec.active:
            skipped.append(f"Faktura {inv.economic_invoice_number}: EconomicCustomer mangler eller inaktiv")
            continue

        if ec.linked_customer_id is None:
            customer = Customer(
                company_id=company_id,
                name=ec.name,
            )
            session.add(customer)
            session.flush()
            ec.linked_customer_id = customer.id
            session.add(ec)

        project = Project(
            id=str(uuid.uuid4()),
            company_id=company_id,
            customer_id=ec.linked_customer_id,
            title=f"Faktura {inv.economic_invoice_number} — {inv.customer_name}",
            status=ProjectStatus.completed,
            end_date=inv.payment_date or inv.due_date,
        )
        session.add(project)
        session.flush()
        inv.linked_project_id = project.id
        session.add(inv)
        created += 1

    session.commit()
    return HistoricalProjectsResult(created=created, skipped=skipped)


# ── clear (preview + execute) ──────────────────────────────────────────────────

class ClearInvoicePreviewResult(BaseModel):
    invoice_count: int
    active_match_count: int
    confirmed_match_count: int
    linked_project_count: int
    warnings: list[str]


class ClearAllInvoicesResult(BaseModel):
    deleted_invoices: int
    deleted_matches: int
    bank_txs_reverted: int


@router.get("/clear-preview", response_model=ClearInvoicePreviewResult)
def clear_invoice_preview(ctx: CompanyContextDep) -> ClearInvoicePreviewResult:
    """Return impact summary before clearing all invoices for the session company.

    Read-only — no data is changed.
    """
    session = ctx.session
    company_id = ctx.company_id

    invoices = session.exec(
        select(EconomicInvoice).where(EconomicInvoice.company_id == company_id)
    ).all()
    if not invoices:
        return ClearInvoicePreviewResult(
            invoice_count=0, active_match_count=0, confirmed_match_count=0,
            linked_project_count=0, warnings=[],
        )

    inv_ids = {inv.id for inv in invoices}
    active_matches = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.economic_invoice_id.in_(inv_ids),
            ReconciliationMatch.active == True,  # noqa: E712
        )
    ).all()
    confirmed_count = sum(1 for m in active_matches if m.confirmed)
    linked_project_count = sum(1 for inv in invoices if inv.linked_project_id is not None)

    warnings: list[str] = []
    if confirmed_count:
        warnings.append(f"{confirmed_count} bekræftede afstemninger vil gå tabt")
    if len(active_matches) - confirmed_count > 0:
        warnings.append(f"{len(active_matches) - confirmed_count} ubekræftede forslag fjernes")
    if linked_project_count:
        warnings.append(
            f"{linked_project_count} fakturaer er tilknyttet projekter — "
            "projekterne bevares men mister fakturalinket"
        )

    return ClearInvoicePreviewResult(
        invoice_count=len(invoices),
        active_match_count=len(active_matches),
        confirmed_match_count=confirmed_count,
        linked_project_count=linked_project_count,
        warnings=warnings,
    )


@router.post("/clear-all", response_model=ClearAllInvoicesResult, status_code=200)
def clear_all_invoices(ctx: CompanyContextDep) -> ClearAllInvoicesResult:
    """Delete all invoices for the session company."""
    session = ctx.session
    company_id = ctx.company_id

    invoices = session.exec(
        select(EconomicInvoice).where(EconomicInvoice.company_id == company_id)
    ).all()
    if not invoices:
        return ClearAllInvoicesResult(deleted_invoices=0, deleted_matches=0, bank_txs_reverted=0)

    inv_ids = {inv.id for inv in invoices}

    all_matches = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.economic_invoice_id.in_(inv_ids)
        )
    ).all()

    tx_ids_to_check = {m.bank_transaction_id for m in all_matches if m.active}
    bank_txs_reverted = 0
    for tx_id in tx_ids_to_check:
        other_active = session.exec(
            select(ReconciliationMatch).where(
                ReconciliationMatch.bank_transaction_id == tx_id,
                ReconciliationMatch.active == True,  # noqa: E712
                ReconciliationMatch.economic_invoice_id.not_in(inv_ids),
            )
        ).first()
        if not other_active:
            tx = session.get(BankTransaction, tx_id)
            if tx and tx.status == BankTransactionStatus.matched:
                tx.status = BankTransactionStatus.unmatched
                session.add(tx)
                bank_txs_reverted += 1

    deleted_matches = len(all_matches)
    for m in all_matches:
        session.delete(m)
    session.flush()

    for inv in invoices:
        session.delete(inv)

    session.commit()
    return ClearAllInvoicesResult(
        deleted_invoices=len(invoices),
        deleted_matches=deleted_matches,
        bank_txs_reverted=bank_txs_reverted,
    )
