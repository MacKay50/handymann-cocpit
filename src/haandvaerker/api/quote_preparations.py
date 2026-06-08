from __future__ import annotations
import json
import uuid
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.company import Company
from ..models.customer import Customer
from ..models.enquiry import Enquiry, EnquirySource, EnquiryStatus
from ..models.inbox_message import InboxMessage
from ..models.project import Project, ProjectStatus
from ..models.quote import (
    Quote, QuoteLine, QuoteSequence, QuoteStatus,
    compute_line_total, compute_quote_totals,
)
from ..models.quote_preparation import (
    QPStatus, QuotePreparation,
    QuotePreparationCreate, QuotePreparationRead, QuotePreparationUpdate,
)
from ..quote_parser import parse_inbox_message
from ..services import wizard_service

class ConvertToFlowRequest(BaseModel):
    source: Optional[str] = None
    send_email: bool = False
    email_subject: Optional[str] = None
    email_body: Optional[str] = None

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            EnquirySource(v)
        except ValueError:
            valid = ", ".join(e.value for e in EnquirySource)
            raise ValueError(f"Invalid source '{v}'. Must be one of: {valid}")
        return v


class ConvertToFlowResponse(BaseModel):
    preparation_id: str
    customer_id: Optional[str] = None
    enquiry_id: Optional[str] = None
    project_id: Optional[str] = None
    quote_id: Optional[str] = None
    email_sent: bool = False
    email_error: Optional[str] = None


router = APIRouter(prefix="/quote-preparations", tags=["quote-preparations"])

VALID_TRANSITIONS: dict[QPStatus, set[QPStatus]] = {
    QPStatus.draft: {QPStatus.reviewed, QPStatus.archived},
    QPStatus.reviewed: {QPStatus.converted, QPStatus.archived},
}


def _apply_transition(qp: QuotePreparation, target: QPStatus) -> None:
    allowed = VALID_TRANSITIONS.get(qp.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{qp.status}' to '{target}'",
        )
    qp.status = target


def _to_read(qp: QuotePreparation) -> QuotePreparationRead:
    return QuotePreparationRead(
        id=qp.id,
        company_id=qp.company_id,
        inbox_message_id=qp.inbox_message_id,
        enquiry_id=qp.enquiry_id,
        project_id=qp.project_id,
        quote_id=qp.quote_id,
        customer_name=qp.customer_name,
        customer_email=qp.customer_email,
        customer_phone=qp.customer_phone,
        address=qp.address,
        task_type=qp.task_type,
        short_summary=qp.short_summary,
        detailed_description=qp.detailed_description,
        suggested_lines=json.loads(qp.suggested_lines_json) if qp.suggested_lines_json else [],
        missing_info=json.loads(qp.missing_info_json) if qp.missing_info_json else [],
        rooms=json.loads(qp.rooms_json) if qp.rooms_json else [],
        internal_notes=qp.internal_notes,
        status=qp.status,
        active=qp.active,
        created_at=qp.created_at,
        updated_at=qp.updated_at,
    )


def _next_quote_number(session: Session) -> str:
    year = date.today().year
    seq = session.get(QuoteSequence, year)
    if seq is None:
        seq = QuoteSequence(year=year, last_number=0)
    seq.last_number += 1
    session.add(seq)
    return f"TIL-{year}-{seq.last_number:03d}"


@router.post("/", response_model=QuotePreparationRead, status_code=201)
def create_preparation(
    data: QuotePreparationCreate, ctx: CompanyContextDep
) -> QuotePreparationRead:
    """Create a QuotePreparation draft directly (wizard path, no inbox message)."""
    session = ctx.session
    preparation_id = data.id or str(uuid.uuid4())
    existing = session.get(QuotePreparation, preparation_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="QuotePreparation with this id already exists")
    now = datetime.utcnow()
    qp = QuotePreparation(
        id=preparation_id,
        company_id=ctx.company_id,
        inbox_message_id=None,
        customer_name=data.customer_name,
        customer_email=data.customer_email,
        customer_phone=data.customer_phone,
        address=data.address,
        task_type=data.task_type,
        short_summary=data.short_summary,
        detailed_description=data.detailed_description,
        internal_notes=data.internal_notes,
        status=QPStatus.draft,
        created_at=now,
        updated_at=now,
    )
    session.add(qp)
    session.commit()
    session.refresh(qp)
    return _to_read(qp)


@router.post(
    "/from-inbox/{inbox_message_id}",
    response_model=QuotePreparationRead,
    status_code=201,
)
def create_from_inbox(inbox_message_id: str, ctx: CompanyContextDep) -> QuotePreparationRead:
    session = ctx.session
    msg = session.get(InboxMessage, inbox_message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    existing = session.exec(
        select(QuotePreparation).where(
            QuotePreparation.inbox_message_id == inbox_message_id,
            QuotePreparation.active == True,  # noqa: E712
        )
    ).first()
    if existing:
        return _to_read(existing)

    parsed = parse_inbox_message(msg)
    now = datetime.utcnow()
    qp = QuotePreparation(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        inbox_message_id=inbox_message_id,
        customer_name=parsed["customer_name"],
        customer_email=parsed["customer_email"],
        customer_phone=parsed["customer_phone"],
        address=parsed["address"],
        task_type=parsed["task_type"],
        short_summary=parsed["short_summary"],
        detailed_description=parsed["detailed_description"],
        suggested_lines_json=json.dumps(parsed["suggested_lines"], ensure_ascii=False),
        missing_info_json=json.dumps(parsed["missing_info"], ensure_ascii=False),
        rooms_json=json.dumps(parsed["rooms"], ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    session.add(qp)
    session.commit()
    session.refresh(qp)
    return _to_read(qp)


@router.get("/", response_model=list[QuotePreparationRead])
def list_preparations(
    ctx: CompanyContextDep,
    active_only: bool = True,
    status: Optional[QPStatus] = None,
) -> list[QuotePreparationRead]:
    session = ctx.session
    query = select(QuotePreparation).where(QuotePreparation.company_id == ctx.company_id)
    if active_only:
        query = query.where(QuotePreparation.active == True)  # noqa: E712
    if status is not None:
        query = query.where(QuotePreparation.status == status)
    return [_to_read(qp) for qp in session.exec(query).all()]


@router.get("/{preparation_id}", response_model=QuotePreparationRead)
def get_preparation(preparation_id: str, ctx: CompanyContextDep) -> QuotePreparationRead:
    session = ctx.session
    qp = session.get(QuotePreparation, preparation_id)
    if not qp:
        raise HTTPException(status_code=404, detail="QuotePreparation not found")
    if qp.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _to_read(qp)


@router.patch("/{preparation_id}", response_model=QuotePreparationRead)
def update_preparation(
    preparation_id: str, data: QuotePreparationUpdate, ctx: CompanyContextDep
) -> QuotePreparationRead:
    session = ctx.session
    qp = session.get(QuotePreparation, preparation_id)
    if not qp:
        raise HTTPException(status_code=404, detail="QuotePreparation not found")
    if qp.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if qp.status not in {QPStatus.draft, QPStatus.reviewed}:
        raise HTTPException(
            status_code=409, detail=f"Cannot update preparation with status '{qp.status}'"
        )
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "suggested_lines":
            qp.suggested_lines_json = (
                json.dumps(value, ensure_ascii=False) if value is not None else None
            )
        elif field == "missing_info":
            qp.missing_info_json = (
                json.dumps(value, ensure_ascii=False) if value is not None else None
            )
        elif field == "rooms":
            qp.rooms_json = (
                json.dumps(value, ensure_ascii=False) if value is not None else None
            )
        else:
            setattr(qp, field, value)
    qp.updated_at = datetime.utcnow()
    session.add(qp)
    session.commit()
    session.refresh(qp)
    return _to_read(qp)


@router.post("/{preparation_id}/review", response_model=QuotePreparationRead)
def mark_reviewed(preparation_id: str, ctx: CompanyContextDep) -> QuotePreparationRead:
    session = ctx.session
    qp = session.get(QuotePreparation, preparation_id)
    if not qp:
        raise HTTPException(status_code=404, detail="QuotePreparation not found")
    if qp.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _apply_transition(qp, QPStatus.reviewed)
    qp.updated_at = datetime.utcnow()
    session.add(qp)
    session.commit()
    session.refresh(qp)
    return _to_read(qp)


@router.post(
    "/{preparation_id}/convert-to-flow",
    response_model=ConvertToFlowResponse,
    status_code=201,
)
def convert_to_flow(
    preparation_id: str,
    ctx: CompanyContextDep,
    body: Optional[ConvertToFlowRequest] = None,
) -> ConvertToFlowResponse:
    session = ctx.session
    qp = session.get(QuotePreparation, preparation_id)
    if not qp:
        raise HTTPException(status_code=404, detail="QuotePreparation not found")
    if qp.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if qp.status == QPStatus.converted:
        return ConvertToFlowResponse(
            preparation_id=qp.id,
            enquiry_id=qp.enquiry_id,
            project_id=qp.project_id,
            quote_id=qp.quote_id,
        )
    if qp.status not in {QPStatus.draft, QPStatus.reviewed}:
        raise HTTPException(
            status_code=409, detail=f"Cannot convert preparation with status '{qp.status}'"
        )
    if not qp.customer_name:
        raise HTTPException(status_code=422, detail="customer_name is required for conversion")

    # Resolve enquiry source
    enquiry_source = EnquirySource(body.source) if body and body.source else EnquirySource.email

    # 1. Create Customer
    customer = Customer(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        name=qp.customer_name,
        email=qp.customer_email,
        phone=qp.customer_phone,
        address=qp.address,
    )
    session.add(customer)
    session.flush()

    # 2. Create Enquiry
    enquiry_title = qp.short_summary or qp.task_type or "Tilbudsforespørgsel"
    enquiry = Enquiry(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        customer_id=customer.id,
        title=enquiry_title[:200],
        source=enquiry_source,
        contact_name=qp.customer_name,
        contact_email=qp.customer_email,
        contact_phone=qp.customer_phone,
        notes=qp.detailed_description,
        status=EnquiryStatus.qualified,
    )
    session.add(enquiry)
    session.flush()

    # 3. Create Project (draft)
    project = Project(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        customer_id=customer.id,
        title=enquiry_title[:200],
        status=ProjectStatus.draft,
        enquiry_id=enquiry.id,
        address=qp.address,
        description=qp.detailed_description,
    )
    session.add(project)
    session.flush()

    enquiry.project_id = project.id
    session.add(enquiry)

    # 4. Create Quote draft with suggested lines
    quote_number = _next_quote_number(session)
    suggested = json.loads(qp.suggested_lines_json) if qp.suggested_lines_json else []
    line_totals = [
        compute_line_total(sl.get("quantity", 1), sl.get("unit_price", 0.0))
        for sl in suggested
    ]
    subtotal, vat, total = compute_quote_totals(line_totals)

    quote = Quote(
        id=str(uuid.uuid4()),
        project_id=project.id,
        company_id=ctx.company_id,
        quote_number=quote_number,
        title=enquiry_title[:200],
        description=qp.detailed_description,
        notes="Foreløbige estimatlinjer — kræver gennemgang inden afsendelse",
        status=QuoteStatus.draft,
        subtotal=subtotal,
        vat_amount=vat,
        total=total,
    )
    session.add(quote)
    session.flush()

    for sl in suggested:
        lt = compute_line_total(sl.get("quantity", 1), sl.get("unit_price", 0.0))
        session.add(QuoteLine(
            id=str(uuid.uuid4()),
            quote_id=quote.id,
            description=sl["description"],
            unit=sl.get("unit", "stk"),
            quantity=float(sl.get("quantity", 1)),
            unit_price=float(sl.get("unit_price", 0.0)),
            line_total=lt,
        ))

    # 5. Mark preparation converted
    qp.status = QPStatus.converted
    qp.enquiry_id = enquiry.id
    qp.project_id = project.id
    qp.quote_id = quote.id
    qp.updated_at = datetime.utcnow()
    session.add(qp)

    session.commit()

    # 6. Optionally send confirmation email (never roll back on failure)
    email_sent = False
    email_error: Optional[str] = None
    if body and body.send_email:
        if not customer.email:
            email_sent = False
            email_error = "Kunde mangler email-adresse"
        else:
            company = session.get(Company, ctx.company_id)
            company_name = company.name if company else ""
            result = wizard_service.send_confirmation_email(
                to=customer.email,
                customer_name=customer.name,
                project_title=project.title,
                company_name=company_name,
                subject_override=body.email_subject or None,
                body_override=body.email_body or None,
            )
            email_sent = bool(result["sent"])
            email_error = result["error"] if not email_sent else None

    return ConvertToFlowResponse(
        preparation_id=qp.id,
        customer_id=customer.id,
        enquiry_id=enquiry.id,
        project_id=project.id,
        quote_id=quote.id,
        email_sent=email_sent,
        email_error=email_error,
    )


@router.delete("/{preparation_id}", status_code=204)
def delete_preparation(preparation_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    qp = session.get(QuotePreparation, preparation_id)
    if not qp:
        raise HTTPException(status_code=404, detail="QuotePreparation not found")
    if qp.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    qp.active = False
    session.add(qp)
    session.commit()
