from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.appointment import Appointment, AppointmentStatus, AppointmentType
from ..models.calendar_suggestion import (
    CalendarSuggestion,
    CalendarSuggestionCreate,
    CalendarSuggestionRead,
    CalendarSuggestionStatus,
    CalendarSuggestionUpdate,
    VALID_SUGGESTION_TRANSITIONS,
)

router = APIRouter(prefix="/calendar-suggestions", tags=["calendar-suggestions"])


def _to_read(s: CalendarSuggestion) -> CalendarSuggestionRead:
    return CalendarSuggestionRead.model_validate(s)


@router.post("/", response_model=CalendarSuggestionRead, status_code=201)
def create_suggestion(
    data: CalendarSuggestionCreate, ctx: CompanyContextDep
) -> CalendarSuggestionRead:
    session = ctx.session
    now = datetime.utcnow()
    suggestion = CalendarSuggestion(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        created_at=now,
        updated_at=now,
        **data.model_dump(),
    )
    session.add(suggestion)
    session.commit()
    session.refresh(suggestion)
    return _to_read(suggestion)


@router.get("/", response_model=list[CalendarSuggestionRead])
def list_suggestions(
    ctx: CompanyContextDep,
    status: Optional[CalendarSuggestionStatus] = None,
    active_only: bool = True,
) -> list[CalendarSuggestionRead]:
    session = ctx.session
    stmt = select(CalendarSuggestion).where(
        CalendarSuggestion.company_id == ctx.company_id
    )
    if active_only:
        stmt = stmt.where(CalendarSuggestion.active == True)  # noqa: E712
    if status:
        stmt = stmt.where(CalendarSuggestion.status == status)
    return [_to_read(s) for s in session.exec(stmt).all()]


@router.get("/{suggestion_id}", response_model=CalendarSuggestionRead)
def get_suggestion(suggestion_id: str, ctx: CompanyContextDep) -> CalendarSuggestionRead:
    session = ctx.session
    s = session.get(CalendarSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="CalendarSuggestion not found")
    if s.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _to_read(s)


@router.patch("/{suggestion_id}", response_model=CalendarSuggestionRead)
def update_suggestion(
    suggestion_id: str, data: CalendarSuggestionUpdate, ctx: CompanyContextDep
) -> CalendarSuggestionRead:
    session = ctx.session
    s = session.get(CalendarSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="CalendarSuggestion not found")
    if s.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if s.status not in {CalendarSuggestionStatus.pending, CalendarSuggestionStatus.approved}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot edit suggestion with status '{s.status}'",
        )
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(s, field, value)
    s.updated_at = datetime.utcnow()
    session.add(s)
    session.commit()
    session.refresh(s)
    return _to_read(s)


@router.post("/{suggestion_id}/approve", response_model=CalendarSuggestionRead)
def approve_suggestion(
    suggestion_id: str, ctx: CompanyContextDep
) -> CalendarSuggestionRead:
    session = ctx.session
    s = session.get(CalendarSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="CalendarSuggestion not found")
    if s.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _transition(s, CalendarSuggestionStatus.approved)
    s.updated_at = datetime.utcnow()
    session.add(s)
    session.commit()
    session.refresh(s)
    return _to_read(s)


@router.post("/{suggestion_id}/reject", response_model=CalendarSuggestionRead)
def reject_suggestion(
    suggestion_id: str, ctx: CompanyContextDep
) -> CalendarSuggestionRead:
    session = ctx.session
    s = session.get(CalendarSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="CalendarSuggestion not found")
    if s.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _transition(s, CalendarSuggestionStatus.rejected)
    s.updated_at = datetime.utcnow()
    session.add(s)
    session.commit()
    session.refresh(s)
    return _to_read(s)


@router.post("/{suggestion_id}/apply", response_model=CalendarSuggestionRead, status_code=201)
def apply_suggestion(
    suggestion_id: str, ctx: CompanyContextDep
) -> CalendarSuggestionRead:
    """Create an Appointment from an approved suggestion. Status → applied."""
    session = ctx.session
    s = session.get(CalendarSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="CalendarSuggestion not found")
    if s.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if s.status != CalendarSuggestionStatus.approved:
        raise HTTPException(
            status_code=409,
            detail=f"Suggestion must be approved before applying (status: '{s.status}')",
        )
    if not s.new_start_at:
        raise HTTPException(status_code=422, detail="new_start_at is required to create appointment")

    end = s.end_at or s.new_start_at
    apt_type_map = {
        "site_visit": AppointmentType.site_visit,
        "meeting": AppointmentType.meeting,
        "estimate": AppointmentType.estimate,
    }
    apt_type = apt_type_map.get(s.event_type.value, AppointmentType.other)

    apt = Appointment(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        project_id=s.project_id,
        title=s.title or "Aftale fra besked",
        location=s.location,
        start_datetime=s.new_start_at,
        end_datetime=end,
        appointment_type=apt_type,
        status=AppointmentStatus.scheduled,
    )
    session.add(apt)
    session.flush()

    s.appointment_id = apt.id
    _transition(s, CalendarSuggestionStatus.applied)
    s.updated_at = datetime.utcnow()
    session.add(s)
    session.commit()
    session.refresh(s)
    return _to_read(s)


@router.delete("/{suggestion_id}", status_code=204)
def delete_suggestion(suggestion_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    s = session.get(CalendarSuggestion, suggestion_id)
    if not s:
        raise HTTPException(status_code=404, detail="CalendarSuggestion not found")
    if s.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    s.active = False
    session.add(s)
    session.commit()


def _transition(
    s: CalendarSuggestion, target: CalendarSuggestionStatus
) -> None:
    allowed = VALID_SUGGESTION_TRANSITIONS.get(s.status.value, [])
    if target.value not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{s.status}' to '{target}'",
        )
    s.status = target
