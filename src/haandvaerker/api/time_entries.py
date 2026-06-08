import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.action_item import ActionItem
from ..models.employee import Employee
from ..models.project import Project
from ..models.time_entry import (
    TimeEntry, TimeEntryCreate, TimeEntryRead, TimeEntrySummary, TimeEntryUpdate,
)
from ..utils import to_decimal

router = APIRouter(prefix="/time-entries", tags=["time-entries"])


def _compute_total(hours: float, hourly_rate: float) -> float:
    result = Decimal(str(hours)) * Decimal(str(hourly_rate))
    return float(result.quantize(Decimal("0.01"), ROUND_HALF_UP))


def _require_active_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' not found")
    if not project.active:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' is inactive")
    return project


def _require_active_employee(employee_id: str, session: Session) -> Employee:
    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' not found")
    if not emp.active:
        raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' is inactive")
    return emp


# summary must be registered before /{time_entry_id} to avoid routing conflict
@router.get("/summary", response_model=TimeEntrySummary)
def get_summary(project_id: str, ctx: CompanyContextDep) -> TimeEntrySummary:
    session = ctx.session
    project = _require_active_project(project_id, session)
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    entries = session.exec(
        select(TimeEntry)
        .where(TimeEntry.project_id == project_id)
        .where(TimeEntry.active == True)  # noqa: E712
    ).all()
    q = Decimal("0.01")
    billable = [e for e in entries if e.billable]
    return TimeEntrySummary(
        project_id=project_id,
        total_hours=float(
            sum(to_decimal(e.hours) for e in entries).quantize(q, ROUND_HALF_UP)
        ),
        total_cost=float(
            sum(to_decimal(e.total) for e in entries).quantize(q, ROUND_HALF_UP)
        ),
        billable_hours=float(
            sum(to_decimal(e.hours) for e in billable).quantize(q, ROUND_HALF_UP)
        ),
        billable_cost=float(
            sum(to_decimal(e.total) for e in billable).quantize(q, ROUND_HALF_UP)
        ),
    )


@router.post("/", response_model=TimeEntryRead, status_code=201)
def create_time_entry(data: TimeEntryCreate, ctx: CompanyContextDep) -> TimeEntryRead:
    session = ctx.session
    project = _require_active_project(data.project_id, session)
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    emp = _require_active_employee(data.employee_id, session)

    # Validate action_item_id if provided.
    # NOTE: SQLite FK enforcement is off (RISK-08) — validated here at app layer.
    warning: Optional[str] = None
    if data.action_item_id is not None:
        action_item = session.get(ActionItem, data.action_item_id)
        if not action_item:
            raise HTTPException(
                status_code=404,
                detail=f"Opgave '{data.action_item_id}' ikke fundet.",
            )
        if action_item.project_id != data.project_id:
            raise HTTPException(
                status_code=422,
                detail="Opgaven tilhører ikke dette projekt.",
            )
        if not action_item.active:
            warning = (
                f"Opgave '{action_item.title}' er arkiveret, "
                "men tidsregistreringen er gemt."
            )

    entry_id = data.id or str(uuid.uuid4())
    effective_rate = data.hourly_rate if data.hourly_rate is not None else emp.default_hourly_rate
    total = _compute_total(data.hours, effective_rate)

    entry = TimeEntry(
        id=entry_id,
        project_id=data.project_id,
        employee_id=data.employee_id,
        company_id=ctx.company_id,
        date=data.date,
        hours=data.hours,
        hourly_rate=effective_rate,
        description=data.description,
        total=total,
        billable=data.billable,
        action_item_id=data.action_item_id,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    read = TimeEntryRead.model_validate(entry)
    read.warning = warning
    return read


@router.get("/", response_model=list[TimeEntryRead])
def list_time_entries(
    ctx: CompanyContextDep,
    active_only: bool = True,
    project_id: Optional[str] = None,
    employee_id: Optional[str] = None,
) -> list[TimeEntryRead]:
    session = ctx.session
    query = select(TimeEntry).where(TimeEntry.company_id == ctx.company_id)
    if active_only:
        query = query.where(TimeEntry.active == True)  # noqa: E712
    if project_id is not None:
        query = query.where(TimeEntry.project_id == project_id)
    if employee_id is not None:
        query = query.where(TimeEntry.employee_id == employee_id)
    return [TimeEntryRead.model_validate(e) for e in session.exec(query).all()]


@router.get("/{time_entry_id}", response_model=TimeEntryRead)
def get_time_entry(time_entry_id: str, ctx: CompanyContextDep) -> TimeEntryRead:
    session = ctx.session
    entry = session.get(TimeEntry, time_entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    if entry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return TimeEntryRead.model_validate(entry)


@router.patch("/{time_entry_id}", response_model=TimeEntryRead)
def update_time_entry(
    time_entry_id: str, data: TimeEntryUpdate, ctx: CompanyContextDep
) -> TimeEntryRead:
    session = ctx.session
    entry = session.get(TimeEntry, time_entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    if entry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    # Validate action_item_id if being set/changed.
    # NOTE: SQLite FK enforcement is off (RISK-08) — validated here at app layer.
    warning: Optional[str] = None
    if "action_item_id" in data.model_fields_set and data.action_item_id is not None:
        action_item = session.get(ActionItem, data.action_item_id)
        if not action_item:
            raise HTTPException(
                status_code=404,
                detail=f"Opgave '{data.action_item_id}' ikke fundet.",
            )
        if action_item.project_id != entry.project_id:
            raise HTTPException(
                status_code=422,
                detail="Opgaven tilhører ikke dette projekt.",
            )
        if not action_item.active:
            warning = (
                f"Opgave '{action_item.title}' er arkiveret, "
                "men tidsregistreringen er gemt."
            )

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, field, value)
    entry.total = _compute_total(entry.hours, entry.hourly_rate)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    read = TimeEntryRead.model_validate(entry)
    read.warning = warning
    return read


@router.delete("/{time_entry_id}", status_code=204)
def deactivate_time_entry(time_entry_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    entry = session.get(TimeEntry, time_entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    if entry.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    entry.active = False
    session.add(entry)
    session.commit()
