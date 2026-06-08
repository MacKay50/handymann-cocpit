import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.customer import Customer
from ..models.enquiry import (
    Enquiry, EnquiryConvert, EnquiryCreate, EnquiryRead,
    EnquirySource, EnquiryStatus, EnquiryUpdate,
)
from ..models.project import Project, ProjectRead, ProjectStatus
from ..services.enquiry_qualification import check_qualification

router = APIRouter(prefix="/enquiries", tags=["enquiries"])

VALID_TRANSITIONS: dict[EnquiryStatus, set[EnquiryStatus]] = {
    EnquiryStatus.new: {EnquiryStatus.qualified, EnquiryStatus.closed},
    EnquiryStatus.qualified: {EnquiryStatus.converted, EnquiryStatus.closed},
}


def _check_transition_allowed(enquiry: Enquiry, target: EnquiryStatus) -> None:
    """Raise 409 if the transition is not allowed; does NOT mutate status."""
    allowed = VALID_TRANSITIONS.get(enquiry.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{enquiry.status}' to '{target}'",
        )


def _apply_transition(enquiry: Enquiry, target: EnquiryStatus) -> None:
    _check_transition_allowed(enquiry, target)
    enquiry.status = target


@router.post("/", response_model=EnquiryRead, status_code=201)
def create_enquiry(data: EnquiryCreate, ctx: CompanyContextDep) -> EnquiryRead:
    session = ctx.session
    if data.customer_id is not None:
        customer = session.get(Customer, data.customer_id)
        if not customer or not customer.active:
            raise HTTPException(status_code=422, detail=f"Customer '{data.customer_id}' not found or inactive")

    enquiry_id = data.id or str(uuid.uuid4())
    if session.get(Enquiry, enquiry_id):
        raise HTTPException(status_code=409, detail=f"Enquiry {enquiry_id} already exists")

    enquiry = Enquiry(
        id=enquiry_id,
        company_id=ctx.company_id,
        customer_id=data.customer_id,
        title=data.title,
        source=data.source,
        contact_name=data.contact_name,
        contact_phone=data.contact_phone,
        contact_email=data.contact_email,
        notes=data.notes,
        address=data.address,
        work_type=data.work_type,
        timeframe=data.timeframe,
    )
    session.add(enquiry)
    session.commit()
    session.refresh(enquiry)
    return EnquiryRead.model_validate(enquiry)


@router.get("/", response_model=list[EnquiryRead])
def list_enquiries(
    ctx: CompanyContextDep,
    active_only: bool = True,
    status: Optional[EnquiryStatus] = None,
    source: Optional[EnquirySource] = None,
) -> list[EnquiryRead]:
    session = ctx.session
    query = select(Enquiry).where(Enquiry.company_id == ctx.company_id)
    if active_only:
        query = query.where(Enquiry.active == True)  # noqa: E712
    if status is not None:
        query = query.where(Enquiry.status == status)
    if source is not None:
        query = query.where(Enquiry.source == source)
    return [EnquiryRead.model_validate(e) for e in session.exec(query).all()]


@router.get("/{enquiry_id}/qualification-status")
def get_qualification_status(enquiry_id: str, ctx: CompanyContextDep) -> dict:
    """Returner kvalifikationsstatus for en forespørgsel.

    Svar: ``{ready, checklist, missing_fields}``
    """
    session = ctx.session
    enquiry = session.get(Enquiry, enquiry_id)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Forespørgsel ikke fundet.")
    if enquiry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    result = check_qualification(enquiry)
    return {
        "ready": result.ready,
        "checklist": result.checklist,
        "missing_fields": result.missing_fields,
    }


@router.get("/{enquiry_id}", response_model=EnquiryRead)
def get_enquiry(enquiry_id: str, ctx: CompanyContextDep) -> EnquiryRead:
    session = ctx.session
    enquiry = session.get(Enquiry, enquiry_id)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if enquiry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return EnquiryRead.model_validate(enquiry)


@router.patch("/{enquiry_id}", response_model=EnquiryRead)
def update_enquiry(enquiry_id: str, data: EnquiryUpdate, ctx: CompanyContextDep) -> EnquiryRead:
    session = ctx.session
    enquiry = session.get(Enquiry, enquiry_id)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if enquiry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if enquiry.status == EnquiryStatus.converted:
        raise HTTPException(status_code=409, detail="Cannot update a converted enquiry")

    if data.customer_id is not None:
        customer = session.get(Customer, data.customer_id)
        if not customer or not customer.active:
            raise HTTPException(status_code=422, detail=f"Customer '{data.customer_id}' not found or inactive")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(enquiry, field, value)
    session.add(enquiry)
    session.commit()
    session.refresh(enquiry)
    return EnquiryRead.model_validate(enquiry)


@router.post("/{enquiry_id}/qualify", response_model=EnquiryRead)
def qualify_enquiry(enquiry_id: str, ctx: CompanyContextDep) -> EnquiryRead:
    session = ctx.session
    enquiry = session.get(Enquiry, enquiry_id)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if enquiry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _apply_transition(enquiry, EnquiryStatus.qualified)
    session.add(enquiry)
    session.commit()
    session.refresh(enquiry)
    return EnquiryRead.model_validate(enquiry)


@router.post("/{enquiry_id}/close", response_model=EnquiryRead)
def close_enquiry(enquiry_id: str, ctx: CompanyContextDep) -> EnquiryRead:
    session = ctx.session
    enquiry = session.get(Enquiry, enquiry_id)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if enquiry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _apply_transition(enquiry, EnquiryStatus.closed)
    session.add(enquiry)
    session.commit()
    session.refresh(enquiry)
    return EnquiryRead.model_validate(enquiry)


@router.post("/{enquiry_id}/convert", response_model=ProjectRead, status_code=201)
def convert_enquiry(enquiry_id: str, data: EnquiryConvert, ctx: CompanyContextDep) -> ProjectRead:
    session = ctx.session
    enquiry = session.get(Enquiry, enquiry_id)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if enquiry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    # State machine check first — wrong status gets 409 before the qual gate.
    _check_transition_allowed(enquiry, EnquiryStatus.converted)

    qualification = check_qualification(enquiry)
    if not qualification.ready:
        raise HTTPException(
            status_code=422,
            detail=(
                "Forespørgslen er ikke kvalificeret til konvertering. "
                f"Manglende felter: {', '.join(qualification.missing_fields)}"
            ),
        )

    customer = session.get(Customer, data.customer_id)
    if not customer or not customer.active:
        raise HTTPException(status_code=422, detail=f"Kunde '{data.customer_id}' ikke fundet eller inaktiv.")
    if customer.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    _apply_transition(enquiry, EnquiryStatus.converted)

    project = Project(
        id=str(uuid.uuid4()),
        company_id=enquiry.company_id,
        customer_id=data.customer_id,
        title=data.project_title,
        status=ProjectStatus.draft,
        enquiry_id=enquiry_id,
    )
    session.add(project)
    session.flush()

    enquiry.project_id = project.id
    session.add(enquiry)
    session.commit()
    session.refresh(project)
    return ProjectRead.model_validate(project)


@router.delete("/{enquiry_id}", status_code=204)
def delete_enquiry(enquiry_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    enquiry = session.get(Enquiry, enquiry_id)
    if not enquiry:
        raise HTTPException(status_code=404, detail="Enquiry not found")
    if enquiry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    enquiry.active = False
    session.add(enquiry)
    session.commit()
