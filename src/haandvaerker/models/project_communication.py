from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class CommunicationType(str, Enum):
    inbound_email = "inbound_email"
    outbound_email = "outbound_email"
    phone_call = "phone_call"
    site_note = "site_note"
    other = "other"


class CommunicationPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class ProjectCommunication(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id", index=True)
    project_id: Optional[str] = Field(
        default=None, foreign_key="project.id", index=True
    )
    inbox_message_id: Optional[str] = Field(
        default=None, foreign_key="inboxmessage.id", index=True
    )
    communication_type: CommunicationType = Field(
        default=CommunicationType.inbound_email
    )
    summary: Optional[str] = Field(default=None, max_length=500)
    body: Optional[str] = Field(default=None)
    priority: CommunicationPriority = Field(default=CommunicationPriority.normal)
    requires_action: bool = Field(default=False)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Read / Create / Update schemas ──────────────────────────────────────────

class ProjectCommunicationCreate(SQLModel):
    project_id: Optional[str] = None
    inbox_message_id: Optional[str] = None
    communication_type: CommunicationType = CommunicationType.inbound_email
    summary: Optional[str] = Field(default=None, max_length=500)
    body: Optional[str] = None
    priority: CommunicationPriority = CommunicationPriority.normal
    requires_action: bool = False


class ProjectCommunicationRead(SQLModel):
    id: str
    company_id: str
    project_id: Optional[str]
    inbox_message_id: Optional[str]
    communication_type: CommunicationType
    summary: Optional[str]
    body: Optional[str]
    priority: CommunicationPriority
    requires_action: bool
    active: bool
    created_at: datetime
    updated_at: datetime


class ProjectCommunicationUpdate(SQLModel):
    project_id: Optional[str] = None
    summary: Optional[str] = Field(default=None, max_length=500)
    body: Optional[str] = None
    priority: Optional[CommunicationPriority] = None
    requires_action: Optional[bool] = None
