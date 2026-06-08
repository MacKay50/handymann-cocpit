import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.action_item import ActionItem
from ..models.customer import Customer
from ..models.project import Project, ProjectCreate, ProjectRead, ProjectStatus, ProjectUpdate
from ..models.time_entry import TimeEntry, TimeSummaryGroup, TimeSummaryEntry
from ..services.project_service import check_completion_status

router = APIRouter(prefix="/projects", tags=["projects"])


def _require_active_customer(customer_id: str, session: Session) -> Customer:
    customer = session.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status_code=422, detail=f"Customer '{customer_id}' not found")
    if not customer.active:
        raise HTTPException(status_code=422, detail=f"Customer '{customer_id}' is inactive")
    return customer


@router.post("/", response_model=ProjectRead, status_code=201)
def create_project(data: ProjectCreate, ctx: CompanyContextDep) -> ProjectRead:
    session = ctx.session
    customer = _require_active_customer(data.customer_id, session)
    if customer.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    project_id = data.id or str(uuid.uuid4())
    if session.get(Project, project_id):
        raise HTTPException(status_code=409, detail=f"Project {project_id} already exists")
    project = Project.model_validate({
        **data.model_dump(exclude={"id"}),
        "id": project_id,
        "company_id": ctx.company_id,
    })
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectRead.model_validate(project)


@router.get("/", response_model=list[ProjectRead])
def list_projects(
    ctx: CompanyContextDep,
    active_only: bool = True,
    customer_id: Optional[str] = None,
    status: Optional[ProjectStatus] = None,
) -> list[ProjectRead]:
    session = ctx.session
    query = select(Project).where(Project.company_id == ctx.company_id)
    if active_only:
        query = query.where(Project.active == True)  # noqa: E712
    if customer_id is not None:
        query = query.where(Project.customer_id == customer_id)
    if status is not None:
        query = query.where(Project.status == status)
    projects = session.exec(query).all()
    return [ProjectRead.model_validate(p) for p in projects]


class CompleteProjectRequest(BaseModel):
    close_reason: Optional[str] = None


@router.get("/{project_id}/completion-status")
def get_completion_status(project_id: str, ctx: CompanyContextDep) -> dict:
    session = ctx.session
    project = session.get(Project, project_id)
    if not project or not project.active:
        raise HTTPException(status_code=404, detail="Projekt ikke fundet.")
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    status = check_completion_status(session, project_id)
    return {
        "ready": status.ready,
        "blockers": [{"type": b.type, "detail": b.detail} for b in status.blockers],
        "warnings": status.warnings,
    }


@router.post("/{project_id}/complete", response_model=ProjectRead)
def complete_project(
    project_id: str,
    data: CompleteProjectRequest,
    ctx: CompanyContextDep,
) -> ProjectRead:
    session = ctx.session
    project = session.get(Project, project_id)
    if not project or not project.active:
        raise HTTPException(status_code=404, detail="Projekt ikke fundet.")
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    completion = check_completion_status(session, project_id)

    if not completion.ready and not data.close_reason:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Projektet kan ikke lukkes — der er uafklarede punkter.",
                "blockers": [{"type": b.type, "detail": b.detail} for b in completion.blockers],
                "warnings": completion.warnings,
            },
        )

    project.status = ProjectStatus.completed
    if data.close_reason:
        project.close_reason = data.close_reason
    if not completion.ready:
        project.close_override = True
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectRead.model_validate(project)


@router.get("/{project_id}/time-summary", response_model=list[TimeSummaryGroup])
def get_time_summary(project_id: str, ctx: CompanyContextDep) -> list[TimeSummaryGroup]:
    session = ctx.session
    project = session.get(Project, project_id)
    if not project or not project.active:
        raise HTTPException(status_code=404, detail="Projekt ikke fundet.")
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    entries = session.exec(
        select(TimeEntry).where(
            TimeEntry.project_id == project_id,
            TimeEntry.active.is_(True),
        )
    ).all()

    groups: dict[str | None, TimeSummaryGroup] = {}
    for entry in entries:
        key = entry.action_item_id
        if key not in groups:
            label = "Generelt"
            if key is not None:
                ai = session.get(ActionItem, key)
                label = ai.title if ai else "Ukendt opgave"
            groups[key] = TimeSummaryGroup(
                action_item_id=key,
                label=label,
                total_hours=0.0,
                entries=[],
            )
        groups[key].total_hours += entry.hours
        groups[key].entries.append(TimeSummaryEntry(
            id=entry.id,
            date=entry.date,
            hours=entry.hours,
            description=entry.description,
            employee_id=entry.employee_id,
        ))

    return list(groups.values())


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: str, ctx: CompanyContextDep) -> ProjectRead:
    session = ctx.session
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(project_id: str, data: ProjectUpdate, ctx: CompanyContextDep) -> ProjectRead:
    session = ctx.session
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    session.add(project)
    session.commit()
    session.refresh(project)
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=204)
def deactivate_project(project_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    project.active = False
    session.add(project)
    session.commit()
