from __future__ import annotations

# R3.CONTRACT-10: fixed routes must be registered before parameterised routes
# in this router. sync-all is declared before /{id}/sync below.

import pathlib
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..dependencies import CompanyContextDep
from ..models.customer import Customer, CustomerRead
from ..models.economic_customer import EconomicCustomer, EconomicCustomerRead
from ..services.danish_csv import ImportResult, decode_csv_bytes, parse_economic_customer_csv

router = APIRouter(prefix="/economic-customers", tags=["economic-customers"])


class SyncResult(BaseModel):
    matched: int
    created: int
    skipped: int
    warnings: list[str]


def _sync_one(ec: EconomicCustomer, session: Session) -> tuple[str, Optional[str]]:
    """
    Returns (outcome, warning_message_or_None).
    outcome is 'matched', 'created', or 'skipped'.
    Skips if: already linked, no cvr_number, or blank name (after strip).
    """
    if ec.linked_customer_id is not None:
        return ("matched", None)

    if ec.cvr_number is None:
        return ("skipped", f"Sprang over Kundenummer {ec.economic_customer_number}: intet CVR-nummer")

    if not ec.name.strip():
        return ("skipped", f"Sprang over Kundenummer {ec.economic_customer_number}: tomt navn")

    customer = session.exec(
        select(Customer).where(
            Customer.cvr_number == ec.cvr_number,
            Customer.company_id == ec.company_id,
            Customer.active.is_(True),
        ).limit(1)
    ).first()

    if customer is not None:
        ec.linked_customer_id = customer.id
        session.add(ec)
        return ("matched", None)

    customer = Customer(
        company_id=ec.company_id,
        name=ec.name,
        address=ec.address,
        cvr_number=ec.cvr_number,
        email=ec.email,
        phone=ec.phone,
        economic_customer_number=ec.economic_customer_number,
    )
    session.add(customer)
    session.flush()
    ec.linked_customer_id = customer.id
    session.add(ec)
    return ("created", None)


@router.post("/import", response_model=ImportResult, status_code=201)
def import_economic_customers(
    file_path: str,
    ctx: CompanyContextDep,
) -> ImportResult:
    """Import e-conomic customer CSV. All-or-nothing: if any row fails validation, 422 with error list."""
    session = ctx.session
    company_id = ctx.company_id

    p = pathlib.Path(file_path)
    if not p.exists():
        raise HTTPException(status_code=422, detail=f"Fil ikke fundet: {file_path}")
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        content = decode_csv_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rows, errors = parse_economic_customer_csv(content, company_id)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    for row in rows:
        customer = EconomicCustomer(**row.model_dump())
        session.add(customer)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Import indeholder allerede importerede kundenumre — ingen rækker er gemt.",
        )

    return ImportResult(rows_imported=len(rows), rows_skipped=0, errors=[])


@router.post("/import-upload", response_model=ImportResult, status_code=201)
async def import_economic_customers_upload(
    ctx: CompanyContextDep,
    file: UploadFile = File(...),
) -> ImportResult:
    """Import e-conomic customer CSV via browser file upload. All-or-nothing."""
    session = ctx.session
    company_id = ctx.company_id
    raw = await file.read()
    try:
        content = decode_csv_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows, errors = parse_economic_customer_csv(content, company_id)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    for row in rows:
        customer = EconomicCustomer(**row.model_dump())
        session.add(customer)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Import indeholder allerede importerede kundenumre — ingen rækker er gemt.",
        )
    return ImportResult(rows_imported=len(rows), rows_skipped=0, errors=[])


# R3.CONTRACT-10: sync-all (fixed path) registered BEFORE /{economic_customer_id}/sync (parameterised)
@router.post("/sync-all", response_model=SyncResult, status_code=200)
def sync_all_economic_customers(ctx: CompanyContextDep) -> SyncResult:
    """Sync all active EconomicCustomers for the session company to Customer records via CVR lookup-or-create."""
    session = ctx.session
    company_id = ctx.company_id

    ecs = session.exec(
        select(EconomicCustomer).where(
            EconomicCustomer.company_id == company_id,
            EconomicCustomer.active.is_(True),
        )
    ).all()

    matched = 0
    created = 0
    skipped = 0
    warnings: list[str] = []

    for ec in ecs:
        outcome, warning = _sync_one(ec, session)
        if outcome == "matched":
            matched += 1
        elif outcome == "created":
            created += 1
        else:
            skipped += 1
        if warning is not None:
            warnings.append(warning)

    session.commit()
    return SyncResult(matched=matched, created=created, skipped=skipped, warnings=warnings)


@router.post("/{economic_customer_id}/sync", response_model=CustomerRead, status_code=200)
def sync_economic_customer(economic_customer_id: str, ctx: CompanyContextDep) -> CustomerRead:
    """Sync a single EconomicCustomer to a Customer record via CVR lookup-or-create."""
    session = ctx.session
    ec = session.get(EconomicCustomer, economic_customer_id)
    if not ec:
        raise HTTPException(status_code=404, detail="EconomicCustomer not found")
    if ec.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if ec.linked_customer_id is not None:
        customer = session.get(Customer, ec.linked_customer_id)
        if not customer:
            raise HTTPException(status_code=500, detail="Linked customer not found")
        return CustomerRead.from_orm_masked(customer)

    if ec.cvr_number is None:
        raise HTTPException(
            status_code=422,
            detail="Kundekort mangler CVR-nummer — kan ikke synkronisere",
        )
    if not ec.name.strip():
        raise HTTPException(
            status_code=422,
            detail="Kundekort har tomt navn — kan ikke oprette kunde",
        )

    _sync_one(ec, session)
    session.commit()
    session.refresh(ec)

    customer = session.get(Customer, ec.linked_customer_id)
    if not customer:
        raise HTTPException(status_code=500, detail="Sync completed but linked customer not found")
    return CustomerRead.from_orm_masked(customer)


@router.get("/", response_model=list[EconomicCustomerRead])
def list_economic_customers(
    ctx: CompanyContextDep,
    active_only: bool = True,
) -> list[EconomicCustomerRead]:
    """List e-conomic customers for the session company."""
    session = ctx.session
    q = select(EconomicCustomer).where(EconomicCustomer.company_id == ctx.company_id)
    if active_only:
        q = q.where(EconomicCustomer.active.is_(True))
    return [EconomicCustomerRead.from_ec(ec) for ec in session.exec(q).all()]
