from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class ActionItemStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class ActionItemPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


VALID_ACTION_ITEM_TRANSITIONS: dict[str, list[str]] = {
    "open": ["in_progress", "done", "cancelled"],
    "in_progress": ["done", "open", "cancelled"],
    "done": [],
    "cancelled": [],
}


class ActionItem(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id", index=True)
    project_id: Optional[str] = Field(
        default=None, foreign_key="project.id", index=True
    )
    inbox_message_id: Optional[str] = Field(
        default=None, foreign_key="inboxmessage.id", index=True
    )
    title: str = Field(max_length=300)
    description: Optional[str] = Field(default=None)
    assigned_to: Optional[str] = Field(default=None, max_length=200)
    due_at: Optional[datetime] = Field(default=None)
    status: ActionItemStatus = Field(default=ActionItemStatus.open)
    priority: ActionItemPriority = Field(default=ActionItemPriority.normal)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Read / Create / Update schemas ──────────────────────────────────────────

class ActionItemCreate(SQLModel):
    project_id: Optional[str] = None
    inbox_message_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    assigned_to: Optional[str] = Field(default=None, max_length=200)
    due_at: Optional[datetime] = None
    priority: ActionItemPriority = ActionItemPriority.normal


class ActionItemRead(SQLModel):
    id: str
    company_id: str
    project_id: Optional[str]
    inbox_message_id: Optional[str]
    title: str
    description: Optional[str]
    assigned_to: Optional[str]
    due_at: Optional[datetime]
    status: ActionItemStatus
    priority: ActionItemPriority
    active: bool
    created_at: datetime
    updated_at: datetime


class ActionItemUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    description: Optional[str] = None
    assigned_to: Optional[str] = Field(default=None, max_length=200)
    due_at: Optional[datetime] = None
    priority: Optional[ActionItemPriority] = None
    project_id: Optional[str] = None
