from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class CalendarSuggestionStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    applied = "applied"


class CalendarEventType(str, Enum):
    site_visit = "site_visit"
    meeting = "meeting"
    estimate = "estimate"
    reschedule = "reschedule"
    other = "other"


VALID_SUGGESTION_TRANSITIONS: dict[str, list[str]] = {
    "pending": ["approved", "rejected"],
    "approved": ["applied", "rejected"],
    "rejected": [],
    "applied": [],
}


class CalendarSuggestion(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id", index=True)
    inbox_message_id: Optional[str] = Field(
        default=None, foreign_key="inboxmessage.id", index=True
    )
    project_id: Optional[str] = Field(
        default=None, foreign_key="project.id", index=True
    )
    event_type: CalendarEventType = Field(default=CalendarEventType.other)
    title: Optional[str] = Field(default=None, max_length=300)
    location: Optional[str] = Field(default=None, max_length=500)
    old_start_at: Optional[datetime] = Field(default=None)
    new_start_at: Optional[datetime] = Field(default=None)
    end_at: Optional[datetime] = Field(default=None)
    date_confidence: Optional[float] = Field(default=None)
    status: CalendarSuggestionStatus = Field(
        default=CalendarSuggestionStatus.pending
    )
    appointment_id: Optional[str] = Field(
        default=None, foreign_key="appointment.id"
    )
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ── Read / Create / Update schemas ──────────────────────────────────────────

class CalendarSuggestionRead(SQLModel):
    id: str
    company_id: str
    inbox_message_id: Optional[str]
    project_id: Optional[str]
    event_type: CalendarEventType
    title: Optional[str]
    location: Optional[str]
    old_start_at: Optional[datetime]
    new_start_at: Optional[datetime]
    end_at: Optional[datetime]
    date_confidence: Optional[float]
    status: CalendarSuggestionStatus
    appointment_id: Optional[str]
    active: bool
    created_at: datetime
    updated_at: datetime


class CalendarSuggestionCreate(SQLModel):
    inbox_message_id: Optional[str] = None
    project_id: Optional[str] = None
    event_type: CalendarEventType = CalendarEventType.other
    title: Optional[str] = Field(default=None, max_length=300)
    location: Optional[str] = Field(default=None, max_length=500)
    old_start_at: Optional[datetime] = None
    new_start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    date_confidence: Optional[float] = None


class CalendarSuggestionUpdate(SQLModel):
    event_type: Optional[CalendarEventType] = None
    title: Optional[str] = Field(default=None, max_length=300)
    location: Optional[str] = Field(default=None, max_length=500)
    old_start_at: Optional[datetime] = None
    new_start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    project_id: Optional[str] = None
