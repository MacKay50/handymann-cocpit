import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.reminder import (
    Reminder, ReminderCreate, ReminderEntityType, ReminderRead,
    ReminderStatus, ReminderUpdate,
)

router = APIRouter(prefix="/reminders", tags=["reminders"])



def _validate_entity_link(
    entity_type: Optional[ReminderEntityType],
    entity_id: Optional[str],
) -> None:
    if (entity_type is None) != (entity_id is None):
        raise HTTPException(
            status_code=422,
            detail="related_entity_type and related_entity_id must both be set or both be absent",
        )


@router.post("/", response_model=ReminderRead, status_code=201)
def create_reminder(data: ReminderCreate, ctx: CompanyContextDep) -> ReminderRead:
    session = ctx.session
    _validate_entity_link(data.related_entity_type, data.related_entity_id)

    reminder_id = data.id or str(uuid.uuid4())
    if session.get(Reminder, reminder_id):
        raise HTTPException(status_code=409, detail=f"Reminder {reminder_id} already exists")

    reminder = Reminder(
        id=reminder_id,
        company_id=ctx.company_id,
        title=data.title,
        message=data.message,
        due_date=data.due_date,
        related_entity_type=data.related_entity_type,
        related_entity_id=data.related_entity_id,
        notes=data.notes,
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return ReminderRead.model_validate(reminder)


@router.get("/", response_model=list[ReminderRead])
def list_reminders(
    ctx: CompanyContextDep,
    active_only: bool = True,
    status: Optional[ReminderStatus] = None,
    related_entity_type: Optional[ReminderEntityType] = None,
    related_entity_id: Optional[str] = None,
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
) -> list[ReminderRead]:
    session = ctx.session
    query = select(Reminder).where(Reminder.company_id == ctx.company_id)
    if active_only:
        query = query.where(Reminder.active == True)  # noqa: E712
    if status is not None:
        query = query.where(Reminder.status == status)
    if related_entity_type is not None:
        query = query.where(Reminder.related_entity_type == related_entity_type)
    if related_entity_id is not None:
        query = query.where(Reminder.related_entity_id == related_entity_id)
    if due_from is not None:
        query = query.where(Reminder.due_date >= due_from)
    if due_to is not None:
        query = query.where(Reminder.due_date <= due_to)
    return [ReminderRead.model_validate(r) for r in session.exec(query).all()]


@router.get("/{reminder_id}", response_model=ReminderRead)
def get_reminder(reminder_id: str, ctx: CompanyContextDep) -> ReminderRead:
    session = ctx.session
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if reminder.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return ReminderRead.model_validate(reminder)


@router.patch("/{reminder_id}", response_model=ReminderRead)
def update_reminder(
    reminder_id: str, data: ReminderUpdate, ctx: CompanyContextDep
) -> ReminderRead:
    session = ctx.session
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if reminder.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if reminder.status != ReminderStatus.pending:
        raise HTTPException(status_code=409, detail="Can only edit pending reminders")

    updates = data.model_dump(exclude_unset=True)

    # Validate entity link consistency in the final state
    final_type = updates.get("related_entity_type", reminder.related_entity_type)
    final_id = updates.get("related_entity_id", reminder.related_entity_id)
    _validate_entity_link(final_type, final_id)

    for field, value in updates.items():
        setattr(reminder, field, value)

    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return ReminderRead.model_validate(reminder)


@router.post("/{reminder_id}/acknowledge", response_model=ReminderRead)
def acknowledge_reminder(reminder_id: str, ctx: CompanyContextDep) -> ReminderRead:
    session = ctx.session
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if reminder.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    reminder.status = ReminderStatus.acknowledged
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return ReminderRead.model_validate(reminder)


@router.delete("/{reminder_id}", status_code=204)
def deactivate_reminder(reminder_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if reminder.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    reminder.active = False
    session.add(reminder)
    session.commit()
