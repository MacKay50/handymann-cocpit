from __future__ import annotations

import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.company import Company
from ..models.customer import Customer, CustomerCreate, CustomerRead, CustomerUpdate, PAYMENT_RATINGS
from ..models.historical_offer import HistoricalOffer, HistoricalOfferRead
from ..models.project import Project, ProjectRead
from ..models.quote import Quote, QuoteRead, QuoteSequence


class AddressHistoryResult(BaseModel):
    projects: list[ProjectRead]
    historical_offers: list[HistoricalOfferRead]


class RepeatJobResult(BaseModel):
    project: ProjectRead
    quote: QuoteRead


class ResetDirectoryResult(BaseModel):
    deactivated: int


router = APIRouter(prefix="/customers", tags=["customers"])


@router.post("/", response_model=CustomerRead, status_code=201)
def create_customer(data: CustomerCreate, ctx: CompanyContextDep) -> CustomerRead:
    session = ctx.session
    company = session.get(Company, ctx.company_id)
    if not company or not company.active:
        raise HTTPException(status_code=422, detail=f"Company '{ctx.company_id}' not found or inactive")
    if data.payment_rating and data.payment_rating not in PAYMENT_RATINGS:
        raise HTTPException(status_code=422, detail=f"payment_rating skal være: {PAYMENT_RATINGS}")
    customer_id = data.id or str(uuid.uuid4())
    existing = session.get(Customer, customer_id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Customer {customer_id} already exists")
    customer = Customer.model_validate({
        **data.model_dump(exclude={"id"}),
        "id": customer_id,
        "company_id": ctx.company_id,
    })
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return CustomerRead.from_orm_masked(customer)


@router.get("/", response_model=list[CustomerRead])
def list_customers(
    ctx: CompanyContextDep,
    active_only: bool = True,
) -> list[CustomerRead]:
    session = ctx.session
    query = select(Customer).where(Customer.company_id == ctx.company_id)
    if active_only:
        query = query.where(Customer.active.is_(True))
    customers = session.exec(query).all()
    return [CustomerRead.from_orm_masked(c) for c in customers]


# ── Fixed sub-paths before parameterised routes ───────────────────────────────

@router.delete("/reset-directory", status_code=200, response_model=ResetDirectoryResult)
def reset_directory(ctx: CompanyContextDep) -> ResetDirectoryResult:
    """Deactivate (soft-delete) ALL customers for the session company.
    Linked projects are preserved — only the customer active flag is cleared.
    """
    session = ctx.session
    company = session.get(Company, ctx.company_id)
    if not company or not company.active:
        raise HTTPException(status_code=422, detail=f"Company '{ctx.company_id}' not found or inactive")
    customers = session.exec(
        select(Customer).where(
            Customer.company_id == ctx.company_id,
            Customer.active == True,  # noqa: E712
        )
    ).all()
    for c in customers:
        c.active = False
        session.add(c)
    session.commit()
    return ResetDirectoryResult(deactivated=len(customers))


@router.get("/{customer_id}/address-history", response_model=AddressHistoryResult)
def get_address_history(
    customer_id: str,
    address: str,
    ctx: CompanyContextDep,
) -> AddressHistoryResult:
    """Return Projects and HistoricalOffers that match the given address substring (case-insensitive)."""
    session = ctx.session
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if customer.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    projects = session.exec(
        select(Project).where(
            Project.company_id == ctx.company_id,
            Project.active.is_(True),
            func.lower(Project.address).contains(address.lower()),
        )
    ).all()

    offers = session.exec(
        select(HistoricalOffer).where(
            HistoricalOffer.active.is_(True),
            func.lower(HistoricalOffer.address).contains(address.lower()),
        )
    ).all()

    return AddressHistoryResult(
        projects=[ProjectRead.model_validate(p) for p in projects],
        historical_offers=[HistoricalOfferRead.model_validate(h) for h in offers],
    )


@router.post("/{customer_id}/repeat-job", response_model=RepeatJobResult, status_code=201)
def create_repeat_job(
    customer_id: str,
    title: str,
    ctx: CompanyContextDep,
    address: Optional[str] = None,
) -> RepeatJobResult:
    """Create a new Project + empty Quote draft for a returning customer in one transaction."""
    session = ctx.session
    if not title:
        raise HTTPException(status_code=422, detail="Titel må ikke være tom")

    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not customer.active:
        raise HTTPException(status_code=422, detail="Kunde er inaktiv")
    if customer.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    project = Project(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        title=title,
        customer_id=customer_id,
        address=address,
    )
    session.add(project)
    session.flush()

    year = date.today().year
    seq = session.get(QuoteSequence, year)
    if seq is None:
        seq = QuoteSequence(year=year, last_number=0)
    seq.last_number += 1
    session.add(seq)
    quote_number = f"TIL-{year}-{seq.last_number:03d}"

    quote = Quote(
        id=str(uuid.uuid4()),
        project_id=project.id,
        company_id=ctx.company_id,
        title=title,
        quote_number=quote_number,
        status="draft",
        subtotal=0.0,
        vat_amount=0.0,
        total=0.0,
    )
    session.add(quote)
    session.commit()
    session.refresh(project)
    session.refresh(quote)
    return RepeatJobResult(
        project=ProjectRead.model_validate(project),
        quote=QuoteRead(**quote.model_dump(), rooms=[], lines=[]),
    )


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(customer_id: str, ctx: CompanyContextDep) -> CustomerRead:
    session = ctx.session
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if customer.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return CustomerRead.from_orm_masked(customer)


@router.patch("/{customer_id}", response_model=CustomerRead)
def update_customer(customer_id: str, data: CustomerUpdate, ctx: CompanyContextDep) -> CustomerRead:
    session = ctx.session
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if customer.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if data.payment_rating is not None and data.payment_rating not in PAYMENT_RATINGS:
        raise HTTPException(status_code=422, detail=f"payment_rating skal være: {PAYMENT_RATINGS}")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    session.add(customer)
    session.commit()
    session.refresh(customer)
    return CustomerRead.from_orm_masked(customer)


@router.delete("/{customer_id}", status_code=204)
def deactivate_customer(customer_id: str, ctx: CompanyContextDep) -> None:
    """Soft-delete: sets active=False. Preserves all linked records."""
    session = ctx.session
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if customer.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    customer.active = False
    session.add(customer)
    session.commit()


@router.delete("/{customer_id}/permanent", status_code=200)
def delete_customer_permanent(customer_id: str, ctx: CompanyContextDep) -> dict:
    """Hard-delete: permanently removes the customer row.
    Returns 422 if the customer has linked projects (delete or reassign them first).
    """
    session = ctx.session
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if customer.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    linked_projects = session.exec(
        select(Project).where(Project.customer_id == customer_id)
    ).all()
    if linked_projects:
        raise HTTPException(
            status_code=422,
            detail=f"Kunden har {len(linked_projects)} tilknyttede projekt(er). "
                   "Slet eller omfordel projekterne først.",
        )

    session.delete(customer)
    session.commit()
    return {"deleted": customer_id, "name": customer.name}
