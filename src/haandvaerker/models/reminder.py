import uuid
from datetime import date
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class ReminderEntityType(str, Enum):
    invoice = "invoice"
    appointment = "appointment"
    project = "project"
    quote = "quote"
    payment = "payment"


class ReminderStatus(str, Enum):
    pending = "pending"
    acknowledged = "acknowledged"


class ReminderCreate(SQLModel):
    id: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    message: Optional[str] = Field(default=None, max_length=1000)
    due_date: date
    related_entity_type: Optional[ReminderEntityType] = None
    related_entity_id: Optional[str] = None
    notes: Optional[str] = None


class Reminder(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    title: str
    message: Optional[str] = None
    due_date: date
    related_entity_type: Optional[ReminderEntityType] = None
    related_entity_id: Optional[str] = None
    status: ReminderStatus = Field(default=ReminderStatus.pending)
    notes: Optional[str] = None
    active: bool = Field(default=True)


class ReminderRead(SQLModel):
    id: str
    company_id: str
    title: str
    message: Optional[str]
    due_date: date
    related_entity_type: Optional[ReminderEntityType]
    related_entity_id: Optional[str]
    status: ReminderStatus
    notes: Optional[str]
    active: bool


class ReminderUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    message: Optional[str] = Field(default=None, max_length=1000)
    due_date: Optional[date] = None
    related_entity_type: Optional[ReminderEntityType] = None
    related_entity_id: Optional[str] = None
    notes: Optional[str] = None
