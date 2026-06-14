import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class InboxSource(str, Enum):
    email = "email"
    phone = "phone"
    website = "website"
    walk_in = "walk_in"
    other = "other"


class InboxStatus(str, Enum):
    unread = "unread"
    read = "read"
    converted = "converted"
    archived = "archived"


class InboxMessage(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    received_at: datetime
    source: InboxSource
    sender_name: Optional[str] = Field(default=None, max_length=200)
    sender_email: Optional[str] = Field(default=None, max_length=200)
    sender_phone: Optional[str] = Field(default=None, max_length=50)
    subject: Optional[str] = Field(default=None, max_length=500)
    body: Optional[str] = Field(default=None)
    status: InboxStatus = Field(default=InboxStatus.unread)
    enquiry_id: Optional[str] = Field(default=None)
    active: bool = Field(default=True)
    processing_error: Optional[str] = Field(default=None)


class InboxMessageCreate(SQLModel):
    id: Optional[str] = None
    received_at: datetime
    source: InboxSource
    sender_name: Optional[str] = Field(default=None, max_length=200)
    sender_email: Optional[str] = Field(default=None, max_length=200)
    sender_phone: Optional[str] = Field(default=None, max_length=50)
    subject: Optional[str] = Field(default=None, max_length=500)
    body: Optional[str] = None


class InboxMessageRead(SQLModel):
    id: str
    company_id: str
    received_at: datetime
    source: InboxSource
    sender_name: Optional[str]
    sender_email: Optional[str]
    sender_phone: Optional[str]
    subject: Optional[str]
    body: Optional[str]
    status: InboxStatus
    enquiry_id: Optional[str]
    active: bool
    processing_error: Optional[str] = None


class InboxMessageConvert(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    source: Optional[str] = None
