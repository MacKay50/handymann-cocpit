"""Unified intake dispatcher.

``POST /intake`` accepts a discriminated-union body and routes to the
appropriate existing create handler.  ``company_id`` is always taken from
the session context (CompanyContextDep) — never from the request body
(RISK-02).

Supported types:
- ``message``       → creates an InboxMessage
- ``project_task``  → creates an ActionItem linked to a project
- ``internal_task`` → creates an ActionItem without a project
"""
import uuid
from datetime import datetime
from typing import Literal, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..dependencies import CompanyContextDep
from ..models.action_item import ActionItem, ActionItemPriority
from ..models.inbox_message import InboxMessage, InboxSource

router = APIRouter(prefix="/intake", tags=["intake"])


# ── Request schemas ────────────────────────────────────────────────────────────

class IntakeMessage(BaseModel):
    type: Literal["message"]
    source: InboxSource
    received_at: Optional[datetime] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    sender_phone: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


class IntakeProjectTask(BaseModel):
    type: Literal["project_task"]
    project_id: str
    title: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: ActionItemPriority = ActionItemPriority.normal


class IntakeInternalTask(BaseModel):
    type: Literal["internal_task"]
    title: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: ActionItemPriority = ActionItemPriority.normal


IntakeBody = Union[IntakeMessage, IntakeProjectTask, IntakeInternalTask]


# ── Response schema ────────────────────────────────────────────────────────────

class IntakeResult(BaseModel):
    type: str
    id: str


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/", response_model=IntakeResult, status_code=201)
def create_intake(data: IntakeBody, ctx: CompanyContextDep) -> IntakeResult:
    """Dispatcher for all new-task intake.

    Routes to the appropriate resource based on ``type``.
    ``company_id`` comes from the session, never the body.
    """
    session = ctx.session

    if data.type == "message":
        msg = InboxMessage(
            id=str(uuid.uuid4()),
            company_id=ctx.company_id,
            received_at=data.received_at or datetime.utcnow(),
            source=data.source,
            sender_name=data.sender_name,
            sender_email=data.sender_email,
            sender_phone=data.sender_phone,
            subject=data.subject,
            body=data.body,
        )
        session.add(msg)
        session.commit()
        session.refresh(msg)
        return IntakeResult(type="message", id=msg.id)

    if data.type == "project_task":
        from ..models.project import Project
        project = session.get(Project, data.project_id)
        if not project or not project.active:
            raise HTTPException(
                status_code=422,
                detail=f"Projekt '{data.project_id}' ikke fundet eller inaktivt.",
            )
        if project.company_id != ctx.company_id:
            raise HTTPException(status_code=403, detail="Adgang nægtet.")
        now = datetime.utcnow()
        item = ActionItem(
            id=str(uuid.uuid4()),
            company_id=ctx.company_id,
            project_id=data.project_id,
            title=data.title,
            description=data.description,
            assigned_to=data.assigned_to,
            due_at=data.due_at,
            priority=data.priority,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return IntakeResult(type="project_task", id=item.id)

    if data.type == "internal_task":
        now = datetime.utcnow()
        item = ActionItem(
            id=str(uuid.uuid4()),
            company_id=ctx.company_id,
            project_id=None,
            title=data.title,
            description=data.description,
            assigned_to=data.assigned_to,
            due_at=data.due_at,
            priority=data.priority,
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return IntakeResult(type="internal_task", id=item.id)

    # Unreachable — Pydantic discriminator handles unknown types.
    raise HTTPException(status_code=422, detail=f"Ukendt intake-type: {data.type!r}")  # pragma: no cover
