import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..database import get_session
from ..dependencies import CompanyContextDep
from ..models.company import Company, CompanyCreate, CompanyRead, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["companies"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/", response_model=CompanyRead, status_code=201)
def create_company(data: CompanyCreate, session: SessionDep) -> CompanyRead:
    company_id = data.id or str(uuid.uuid4())
    if session.get(Company, company_id):
        raise HTTPException(status_code=409, detail=f"Company {company_id} already exists")
    company = Company(
        id=company_id,
        name=data.name,
        cvr_number=data.cvr_number,
        address=data.address,
        phone=data.phone,
        email=data.email,
        logo_ref=data.logo_ref,
    )
    session.add(company)
    session.commit()
    session.refresh(company)
    return CompanyRead.from_orm_masked(company)


@router.get("/", response_model=list[CompanyRead])
def list_companies(session: SessionDep, active_only: bool = True) -> list[CompanyRead]:
    query = select(Company)
    if active_only:
        query = query.where(Company.active == True)  # noqa: E712
    return [CompanyRead.from_orm_masked(c) for c in session.exec(query).all()]


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(company_id: str, session: SessionDep) -> CompanyRead:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return CompanyRead.from_orm_masked(company)


@router.patch("/{company_id}", response_model=CompanyRead)
def update_company(company_id: str, data: CompanyUpdate, session: SessionDep) -> CompanyRead:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    session.add(company)
    session.commit()
    session.refresh(company)
    return CompanyRead.from_orm_masked(company)


@router.delete("/{company_id}", status_code=204)
def deactivate_company(company_id: str, session: SessionDep) -> None:
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.active = False
    session.add(company)
    session.commit()
