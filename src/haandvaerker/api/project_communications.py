from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.project_communication import (
    ProjectCommunication,
    ProjectCommunicationCreate,
    ProjectCommunicationRead,
    ProjectCommunicationUpdate,
)

router = APIRouter(prefix="/project-communications", tags=["project-communications"])


@router.post("/", response_model=ProjectCommunicationRead, status_code=201)
def create_communication(
    data: ProjectCommunicationCreate, ctx: CompanyContextDep
) -> ProjectCommunicationRead:
    session = ctx.session
    now = datetime.utcnow()
    comm = ProjectCommunication(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        created_at=now,
        updated_at=now,
        **data.model_dump(),
    )
    session.add(comm)
    session.commit()
    session.refresh(comm)
    return ProjectCommunicationRead.model_validate(comm)


@router.get("/", response_model=list[ProjectCommunicationRead])
def list_communications(
    ctx: CompanyContextDep,
    project_id: Optional[str] = None,
    active_only: bool = True,
) -> list[ProjectCommunicationRead]:
    session = ctx.session
    stmt = select(ProjectCommunication).where(
        ProjectCommunication.company_id == ctx.company_id
    )
    if active_only:
        stmt = stmt.where(ProjectCommunication.active == True)  # noqa: E712
    if project_id:
        stmt = stmt.where(ProjectCommunication.project_id == project_id)
    return [
        ProjectCommunicationRead.model_validate(c) for c in session.exec(stmt).all()
    ]


@router.get("/{comm_id}", response_model=ProjectCommunicationRead)
def get_communication(comm_id: str, ctx: CompanyContextDep) -> ProjectCommunicationRead:
    session = ctx.session
    comm = session.get(ProjectCommunication, comm_id)
    if not comm:
        raise HTTPException(status_code=404, detail="ProjectCommunication not found")
    if comm.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return ProjectCommunicationRead.model_validate(comm)


@router.patch("/{comm_id}", response_model=ProjectCommunicationRead)
def update_communication(
    comm_id: str, data: ProjectCommunicationUpdate, ctx: CompanyContextDep
) -> ProjectCommunicationRead:
    session = ctx.session
    comm = session.get(ProjectCommunication, comm_id)
    if not comm:
        raise HTTPException(status_code=404, detail="ProjectCommunication not found")
    if comm.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(comm, field, value)
    comm.updated_at = datetime.utcnow()
    session.add(comm)
    session.commit()
    session.refresh(comm)
    return ProjectCommunicationRead.model_validate(comm)


@router.delete("/{comm_id}", status_code=204)
def delete_communication(comm_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    comm = session.get(ProjectCommunication, comm_id)
    if not comm:
        raise HTTPException(status_code=404, detail="ProjectCommunication not found")
    if comm.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    comm.active = False
    session.add(comm)
    session.commit()
