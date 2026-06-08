import uuid
from datetime import date, datetime, time
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.appointment import (
    Appointment, AppointmentCreate, AppointmentRead,
    AppointmentStatus, AppointmentUpdate,
)
from ..models.employee import Employee
from ..models.project import Project

router = APIRouter(prefix="/appointments", tags=["appointments"])


VALID_TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    AppointmentStatus.scheduled: {
        AppointmentStatus.completed,
        AppointmentStatus.cancelled,
    },
}


def _require_active_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' not found")
    if not project.active:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' is inactive")
    return project


def _require_active_employee(employee_id: str, session: Session) -> Employee:
    employee = session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' not found")
    if not employee.active:
        raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' is inactive")
    return employee


def _apply_transition(
    appointment: Appointment, target: AppointmentStatus, session: Session
) -> AppointmentRead:
    allowed = VALID_TRANSITIONS.get(appointment.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{appointment.status}' to '{target}'",
        )
    appointment.status = target
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return AppointmentRead.model_validate(appointment)


@router.post("/", response_model=AppointmentRead, status_code=201)
def create_appointment(data: AppointmentCreate, ctx: CompanyContextDep) -> AppointmentRead:
    session = ctx.session
    if data.end_datetime < data.start_datetime:
        raise HTTPException(status_code=422, detail="end_datetime must be >= start_datetime")

    customer_id = data.customer_id
    if data.project_id is not None:
        project = _require_active_project(data.project_id, session)
        if project.company_id != ctx.company_id:
            raise HTTPException(status_code=403, detail="Adgang nægtet.")
        if customer_id is None:
            customer_id = project.customer_id

    if data.employee_id is not None:
        _require_active_employee(data.employee_id, session)

    appointment_id = data.id or str(uuid.uuid4())
    if session.get(Appointment, appointment_id):
        raise HTTPException(status_code=409, detail=f"Appointment {appointment_id} already exists")

    appointment = Appointment(
        id=appointment_id,
        company_id=ctx.company_id,
        customer_id=customer_id,
        project_id=data.project_id,
        employee_id=data.employee_id,
        title=data.title,
        description=data.description,
        start_datetime=data.start_datetime,
        end_datetime=data.end_datetime,
        location=data.location,
        appointment_type=data.appointment_type,
        notes=data.notes,
    )
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return AppointmentRead.model_validate(appointment)


@router.get("/", response_model=list[AppointmentRead])
def list_appointments(
    ctx: CompanyContextDep,
    active_only: bool = True,
    project_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    status: Optional[AppointmentStatus] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[AppointmentRead]:
    session = ctx.session
    query = select(Appointment).where(Appointment.company_id == ctx.company_id)
    if active_only:
        query = query.where(Appointment.active == True)  # noqa: E712
    if project_id is not None:
        query = query.where(Appointment.project_id == project_id)
    if customer_id is not None:
        query = query.where(Appointment.customer_id == customer_id)
    if employee_id is not None:
        query = query.where(Appointment.employee_id == employee_id)
    if status is not None:
        query = query.where(Appointment.status == status)
    if date_from is not None:
        query = query.where(
            Appointment.start_datetime >= datetime.combine(date_from, time.min)
        )
    if date_to is not None:
        query = query.where(
            Appointment.start_datetime <= datetime.combine(date_to, time.max)
        )
    return [AppointmentRead.model_validate(a) for a in session.exec(query).all()]


@router.get("/{appointment_id}", response_model=AppointmentRead)
def get_appointment(appointment_id: str, ctx: CompanyContextDep) -> AppointmentRead:
    session = ctx.session
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return AppointmentRead.model_validate(appointment)


@router.patch("/{appointment_id}", response_model=AppointmentRead)
def update_appointment(
    appointment_id: str, data: AppointmentUpdate, ctx: CompanyContextDep
) -> AppointmentRead:
    session = ctx.session
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if appointment.status != AppointmentStatus.scheduled:
        raise HTTPException(status_code=409, detail="Can only edit scheduled appointments")

    if data.employee_id is not None:
        _require_active_employee(data.employee_id, session)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(appointment, field, value)

    start = appointment.start_datetime
    end = appointment.end_datetime
    if end < start:
        raise HTTPException(status_code=422, detail="end_datetime must be >= start_datetime")

    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return AppointmentRead.model_validate(appointment)


@router.delete("/{appointment_id}", status_code=204)
def deactivate_appointment(appointment_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    appointment.active = False
    session.add(appointment)
    session.commit()


@router.post("/{appointment_id}/complete", response_model=AppointmentRead)
def complete_appointment(appointment_id: str, ctx: CompanyContextDep) -> AppointmentRead:
    session = ctx.session
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(appointment, AppointmentStatus.completed, session)


@router.post("/{appointment_id}/cancel", response_model=AppointmentRead)
def cancel_appointment(appointment_id: str, ctx: CompanyContextDep) -> AppointmentRead:
    session = ctx.session
    appointment = session.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(appointment, AppointmentStatus.cancelled, session)
