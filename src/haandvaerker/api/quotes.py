from __future__ import annotations
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlmodel import Session, select
from ..database import get_session
from ..dependencies import CompanyContextDep
from ..models.company import Company
from ..models.customer import Customer
from ..models.invoice import (
    Invoice, InvoiceLine, InvoiceSequence, InvoiceStatus,
    compute_invoice_totals, compute_line_total as inv_compute_line_total,
)
from ..models.project import Project, ProjectStatus
from ..models.quote import (
    Quote, QuoteCreate, QuotePublicRead, QuoteRead, QuoteRejectBody,
    QuoteRoom, QuoteRoomRead,
    QuoteLine, QuoteLineRead, QuoteSequence, QuoteStatus,
    QuoteUpdate, compute_line_total, compute_quote_totals, compute_room_m2,
)
from ..pdf.quote_pdf import generate_quote_pdf
from ..services.offer_from_quote import create_historical_offer_from_quote

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quotes", tags=["quotes"])

SessionDep = Annotated[Session, Depends(get_session)]

VALID_TRANSITIONS: dict[QuoteStatus, set[QuoteStatus]] = {
    QuoteStatus.draft: {QuoteStatus.sent},
    QuoteStatus.sent: {QuoteStatus.accepted, QuoteStatus.rejected},
}


def _require_active_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' not found")
    if not project.active:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' is inactive")
    return project


def _next_quote_number(session: Session) -> str:
    year = date.today().year
    seq = session.get(QuoteSequence, year)
    if seq is None:
        seq = QuoteSequence(year=year, last_number=0)
    seq.last_number += 1
    session.add(seq)
    return f"TIL-{year}-{seq.last_number:03d}"


def _build_rooms(quote_id: str, room_creates: list, session: Session) -> list[QuoteRoom]:
    rooms = []
    for rc in room_creates:
        room = QuoteRoom(
            id=str(uuid.uuid4()),
            quote_id=quote_id,
            **rc.model_dump(),
        )
        session.add(room)
        rooms.append(room)
    return rooms


def _build_lines(quote_id: str, line_creates: list, session: Session) -> list[QuoteLine]:
    lines = []
    for lc in line_creates:
        lt = compute_line_total(lc.quantity, lc.unit_price)
        line = QuoteLine(
            id=str(uuid.uuid4()),
            quote_id=quote_id,
            line_total=lt,
            **lc.model_dump(),
        )
        session.add(line)
        lines.append(line)
    return lines


def _build_quote_read(quote: Quote, session: Session) -> QuoteRead:
    rooms = session.exec(select(QuoteRoom).where(QuoteRoom.quote_id == quote.id)).all()
    lines = session.exec(select(QuoteLine).where(QuoteLine.quote_id == quote.id)).all()

    room_reads = [
        QuoteRoomRead(**{**room.model_dump(), **compute_room_m2(room)})
        for room in rooms
    ]
    line_reads = [QuoteLineRead.model_validate(line) for line in lines]

    return QuoteRead(**{**quote.model_dump(), "rooms": room_reads, "lines": line_reads})


def _build_public_read(quote: Quote, session: Session) -> QuotePublicRead:
    company = session.get(Company, quote.company_id)
    lines = session.exec(select(QuoteLine).where(QuoteLine.quote_id == quote.id)).all()
    return QuotePublicRead(
        quote_number=quote.quote_number,
        title=quote.title,
        description=quote.description,
        valid_until=quote.valid_until,
        notes=quote.notes,
        status=quote.status,
        subtotal=quote.subtotal,
        vat_amount=quote.vat_amount,
        total=quote.total,
        accepted_at=quote.accepted_at,
        rejected_at=quote.rejected_at,
        rejection_reason=quote.rejection_reason,
        company_name=company.name if company else "—",
        company_logo_url=company.logo_ref if company else None,
        lines=[QuoteLineRead.model_validate(ln) for ln in lines],
    )


def _get_by_token(token: str, session: Session) -> Quote:
    quote = session.exec(
        select(Quote).where(Quote.accept_token == token)
    ).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found for this token")
    return quote


def _apply_transition(quote: Quote, target: QuoteStatus, session: Session) -> QuoteRead:
    allowed = VALID_TRANSITIONS.get(quote.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{quote.status}' to '{target}'",
        )
    quote.status = target
    session.add(quote)
    session.commit()
    session.refresh(quote)
    return _build_quote_read(quote, session)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=QuoteRead, status_code=201)
def create_quote(data: QuoteCreate, ctx: CompanyContextDep) -> QuoteRead:
    session = ctx.session
    project = _require_active_project(data.project_id, session)
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    quote_type = data.quote_type
    if quote_type not in ("line", "area"):
        raise HTTPException(status_code=422, detail="quote_type skal være 'line' eller 'area'.")

    if quote_type == "line" and data.rooms:
        raise HTTPException(status_code=422, detail="Linjebaserede tilbud må ikke indeholde rum.")

    if quote_type == "area" and data.lines:
        raise HTTPException(status_code=422, detail="Arealbaserede tilbud må ikke indeholde linjer.")

    if quote_type == "area":
        for i, room in enumerate(data.rooms):
            if room.price_per_m2 is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Rum {i + 1} mangler pris pr. m² (price_per_m2). Arealbaserede tilbud kræver pris pr. m² på alle rum.",
                )

    quote_id = data.id or str(uuid.uuid4())
    if session.get(Quote, quote_id):
        raise HTTPException(status_code=409, detail=f"Quote {quote_id} already exists")

    quote_number = _next_quote_number(session)
    header = data.model_dump(exclude={"id", "rooms", "lines"})
    quote = Quote(**header, id=quote_id, quote_number=quote_number, company_id=ctx.company_id)

    if quote_type == "area":
        _build_rooms(quote_id, data.rooms, session)
        subtotal = sum(
            room.length_m * room.width_m * room.price_per_m2  # type: ignore[operator]
            for room in data.rooms
        )
        subtotal_f, vat, total = compute_quote_totals([subtotal])
        quote.subtotal, quote.vat_amount, quote.total = subtotal_f, vat, total
    else:
        lines = _build_lines(quote_id, data.lines, session)
        subtotal, vat, total = compute_quote_totals([ln.line_total for ln in lines])
        quote.subtotal, quote.vat_amount, quote.total = subtotal, vat, total

    session.add(quote)
    session.commit()
    session.refresh(quote)
    return _build_quote_read(quote, session)


@router.get("/", response_model=list[QuoteRead])
def list_quotes(
    ctx: CompanyContextDep,
    active_only: bool = True,
    project_id: Optional[str] = None,
    status: Optional[QuoteStatus] = None,
) -> list[QuoteRead]:
    session = ctx.session
    query = select(Quote).where(Quote.company_id == ctx.company_id)
    if active_only:
        query = query.where(Quote.active.is_(True))  # type: ignore[union-attr]
    if project_id is not None:
        query = query.where(Quote.project_id == project_id)
    if status is not None:
        query = query.where(Quote.status == status)
    return [_build_quote_read(q, session) for q in session.exec(query).all()]


@router.get("/{quote_id}/pdf")
def get_quote_pdf(quote_id: str, ctx: CompanyContextDep) -> Response:
    session = ctx.session
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    project = session.get(Project, quote.project_id)
    company = session.get(Company, quote.company_id) if quote.company_id else None
    customer = session.get(Customer, project.customer_id) if project else None
    lines = session.exec(
        select(QuoteLine).where(QuoteLine.quote_id == quote_id)
    ).all()

    cvr_raw = company.cvr_number if company else None
    cvr_masked = f"****{cvr_raw[-4:]}" if cvr_raw and len(cvr_raw) >= 4 else None
    pdf_bytes = generate_quote_pdf(
        quote_number=quote.quote_number,
        title=quote.title,
        valid_until=quote.valid_until,
        notes=quote.notes,
        company_name=company.name if company else "—",
        company_address=company.address if company else None,
        company_cvr_masked=cvr_masked,
        customer_name=customer.name if customer else "—",
        customer_address=customer.address if customer else None,
        project_title=project.title if project else "—",
        subtotal=quote.subtotal,
        vat_amount=quote.vat_amount,
        total=quote.total,
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
    filename = f"{quote.quote_number}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/{quote_id}", response_model=QuoteRead)
def get_quote(quote_id: str, ctx: CompanyContextDep) -> QuoteRead:
    session = ctx.session
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _build_quote_read(quote, session)


@router.patch("/{quote_id}", response_model=QuoteRead)
def update_quote(quote_id: str, data: QuoteUpdate, ctx: CompanyContextDep) -> QuoteRead:
    session = ctx.session
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if quote.status != QuoteStatus.draft:
        raise HTTPException(status_code=409, detail="Can only edit draft quotes")

    # Determine effective type after this PATCH
    effective_type = data.quote_type if data.quote_type is not None else quote.quote_type

    if data.quote_type is not None and data.quote_type not in ("line", "area"):
        raise HTTPException(status_code=422, detail="quote_type skal være 'line' eller 'area'.")

    # Type-change: clear the incompatible collection
    if data.quote_type is not None and data.quote_type != quote.quote_type:
        if data.quote_type == "line":
            for r in session.exec(select(QuoteRoom).where(QuoteRoom.quote_id == quote_id)).all():
                session.delete(r)
            session.flush()
        elif data.quote_type == "area":
            for ln in session.exec(select(QuoteLine).where(QuoteLine.quote_id == quote_id)).all():
                session.delete(ln)
            session.flush()

    # Cross-type pollution guard for new collections provided in this PATCH
    if effective_type == "line" and data.rooms:
        raise HTTPException(status_code=422, detail="Linjebaserede tilbud må ikke indeholde rum.")
    if effective_type == "area" and data.lines:
        raise HTTPException(status_code=422, detail="Arealbaserede tilbud må ikke indeholde linjer.")

    for field, value in data.model_dump(exclude_unset=True, exclude={"rooms", "lines"}).items():
        setattr(quote, field, value)

    if data.rooms is not None:
        if effective_type == "area" and len(data.rooms) == 0:
            raise HTTPException(
                status_code=422,
                detail="Arealbaserede tilbud kræver mindst ét rum.",
            )
        if effective_type == "area":
            for i, room in enumerate(data.rooms):
                if room.price_per_m2 is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Rum {i + 1} mangler pris pr. m² — arealbaserede tilbud kræver price_per_m2 på alle rum.",
                    )
        for old in session.exec(select(QuoteRoom).where(QuoteRoom.quote_id == quote_id)).all():
            session.delete(old)
        session.flush()
        _build_rooms(quote_id, data.rooms, session)
        if effective_type == "area":
            subtotal = sum(
                room.length_m * room.width_m * room.price_per_m2  # type: ignore[operator]
                for room in data.rooms
            )
            subtotal_f, vat, total = compute_quote_totals([subtotal])
            quote.subtotal, quote.vat_amount, quote.total = subtotal_f, vat, total

    if data.lines is not None:
        for old in session.exec(select(QuoteLine).where(QuoteLine.quote_id == quote_id)).all():
            session.delete(old)
        session.flush()
        new_lines = _build_lines(quote_id, data.lines, session)
        subtotal, vat, total = compute_quote_totals([ln.line_total for ln in new_lines])
        quote.subtotal, quote.vat_amount, quote.total = subtotal, vat, total

    session.add(quote)
    session.commit()
    session.refresh(quote)
    return _build_quote_read(quote, session)


@router.delete("/{quote_id}", status_code=204)
def deactivate_quote(quote_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    quote.active = False
    session.add(quote)
    session.commit()


@router.post("/{quote_id}/send", response_model=QuoteRead)
def send_quote(quote_id: str, ctx: CompanyContextDep) -> QuoteRead:
    session = ctx.session
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if not quote.accept_token:
        quote.accept_token = str(uuid.uuid4())
        session.add(quote)
        session.flush()
    return _apply_transition(quote, QuoteStatus.sent, session)


@router.get("/by-token/{token}", response_model=QuotePublicRead)
def get_by_token(token: str, session: SessionDep) -> QuotePublicRead:
    return _build_public_read(_get_by_token(token, session), session)


@router.post("/by-token/{token}/accept", response_model=QuotePublicRead)
def accept_by_token(token: str, session: SessionDep) -> QuotePublicRead:
    quote = _get_by_token(token, session)
    if quote.status != QuoteStatus.sent:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot accept quote with status '{quote.status}'",
        )
    quote.status = QuoteStatus.accepted
    quote.accepted_at = datetime.utcnow()
    session.add(quote)

    # Auto-activate the project
    project = session.get(Project, quote.project_id)
    if project and project.status == ProjectStatus.draft:
        project.status = ProjectStatus.active
        session.add(project)

    session.commit()
    session.refresh(quote)

    try:
        create_historical_offer_from_quote(session, quote)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(
            "erfaringsbank: failed to create HistoricalOffer for quote %s: %s",
            quote.id,
            exc,
        )

    return _build_public_read(quote, session)


@router.post("/by-token/{token}/reject", response_model=QuotePublicRead)
def reject_by_token(
    token: str, body: QuoteRejectBody, session: SessionDep
) -> QuotePublicRead:
    quote = _get_by_token(token, session)
    if quote.status != QuoteStatus.sent:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reject quote with status '{quote.status}'",
        )
    quote.status = QuoteStatus.rejected
    quote.rejected_at = datetime.utcnow()
    quote.rejection_reason = body.reason
    session.add(quote)
    session.commit()
    session.refresh(quote)
    return _build_public_read(quote, session)


def _next_invoice_number(session: Session) -> str:
    year = date.today().year
    seq = session.get(InvoiceSequence, year)
    if seq is None:
        seq = InvoiceSequence(year=year, last_number=0)
    seq.last_number += 1
    session.add(seq)
    return f"FAKT-{year}-{seq.last_number:03d}"


def _create_invoice_from_quote(quote: Quote, project: Project, session: Session) -> Invoice:
    today = date.today()
    invoice_id = str(uuid.uuid4())
    invoice_number = _next_invoice_number(session)

    inv_lines = []
    if quote.quote_type == "area":
        rooms = session.exec(select(QuoteRoom).where(QuoteRoom.quote_id == quote.id)).all()
        if not rooms:
            raise HTTPException(
                status_code=422,
                detail="Arealbaseret tilbud har ingen rum — kan ikke oprette faktura.",
            )
        for room in rooms:
            if room.price_per_m2 is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"Rum '{room.name}' mangler pris pr. m² — kan ikke oprette faktura.",
                )
            m2 = room.length_m * room.width_m
            lt = inv_compute_line_total(m2, room.price_per_m2)
            il = InvoiceLine(
                id=str(uuid.uuid4()),
                invoice_id=invoice_id,
                description=room.name,
                unit="m2",
                quantity=m2,
                unit_price=room.price_per_m2,
                line_total=lt,
            )
            session.add(il)
            inv_lines.append(il)
    else:
        quote_lines = session.exec(select(QuoteLine).where(QuoteLine.quote_id == quote.id)).all()
        for ql in quote_lines:
            lt = inv_compute_line_total(ql.quantity, ql.unit_price)
            il = InvoiceLine(
                id=str(uuid.uuid4()),
                invoice_id=invoice_id,
                description=ql.description,
                unit=ql.unit.value,
                quantity=ql.quantity,
                unit_price=ql.unit_price,
                line_total=lt,
            )
            session.add(il)
            inv_lines.append(il)

    subtotal, vat, total = compute_invoice_totals([il.line_total for il in inv_lines])
    invoice = Invoice(
        id=invoice_id,
        project_id=quote.project_id,
        company_id=quote.company_id,
        customer_id=project.customer_id,
        invoice_number=invoice_number,
        title=f"Faktura – {quote.title}",
        issue_date=today,
        due_date=today + timedelta(days=30),
        subtotal=subtotal,
        vat_amount=vat,
        total=total,
        status=InvoiceStatus.draft,
    )
    session.add(invoice)
    session.flush()
    return invoice


@router.post("/{quote_id}/accept", response_model=QuoteRead)
def accept_quote(quote_id: str, ctx: CompanyContextDep) -> QuoteRead:
    session = ctx.session
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    allowed = VALID_TRANSITIONS.get(quote.status, set())
    if QuoteStatus.accepted not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{quote.status}' to 'accepted'",
        )

    quote.status = QuoteStatus.accepted

    project = session.get(Project, quote.project_id)
    if project and project.status == ProjectStatus.draft:
        project.status = ProjectStatus.active
        session.add(project)

    if project:
        invoice = _create_invoice_from_quote(quote, project, session)
        quote.invoice_id = invoice.id

    session.add(quote)
    session.commit()
    session.refresh(quote)

    try:
        create_historical_offer_from_quote(session, quote)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(
            "erfaringsbank: failed to create HistoricalOffer for quote %s: %s",
            quote.id,
            exc,
        )

    return _build_quote_read(quote, session)


@router.post("/{quote_id}/reject", response_model=QuoteRead)
def reject_quote(quote_id: str, ctx: CompanyContextDep) -> QuoteRead:
    session = ctx.session
    quote = session.get(Quote, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(quote, QuoteStatus.rejected, session)
