from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class QPStatus(str, Enum):
    draft = "draft"
    reviewed = "reviewed"
    converted = "converted"
    archived = "archived"


class QuotePreparation(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    inbox_message_id: Optional[str] = Field(default=None)
    enquiry_id: Optional[str] = Field(default=None)
    project_id: Optional[str] = Field(default=None)
    quote_id: Optional[str] = Field(default=None)

    customer_name: Optional[str] = Field(default=None, max_length=200)
    customer_email: Optional[str] = Field(default=None, max_length=200)
    customer_phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = Field(default=None, max_length=500)
    task_type: Optional[str] = Field(default=None, max_length=200)
    job_notes: Optional[str] = Field(default=None)
    short_summary: Optional[str] = Field(default=None, max_length=500)
    detailed_description: Optional[str] = Field(default=None)

    rooms_json: Optional[str] = Field(default=None)
    suggested_lines_json: Optional[str] = Field(default=None)
    missing_info_json: Optional[str] = Field(default=None)
    internal_notes: Optional[str] = Field(default=None)

    status: QPStatus = Field(default=QPStatus.draft)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class QuotePreparationRead(SQLModel):
    id: str
    company_id: str
    inbox_message_id: Optional[str]
    enquiry_id: Optional[str]
    project_id: Optional[str]
    quote_id: Optional[str]
    customer_name: Optional[str]
    customer_email: Optional[str]
    customer_phone: Optional[str]
    address: Optional[str]
    task_type: Optional[str]
    job_notes: Optional[str] = None
    short_summary: Optional[str]
    detailed_description: Optional[str]
    suggested_lines: list[dict] = []
    missing_info: list[str] = []
    rooms: list[dict] = []
    internal_notes: Optional[str]
    status: QPStatus
    active: bool
    created_at: datetime
    updated_at: datetime


class QuotePreparationUpdate(SQLModel):
    customer_name: Optional[str] = Field(default=None, max_length=200)
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    address: Optional[str] = None
    task_type: Optional[str] = None
    job_notes: Optional[str] = None
    short_summary: Optional[str] = None
    detailed_description: Optional[str] = None
    suggested_lines: Optional[list[dict]] = None
    missing_info: Optional[list[str]] = None
    rooms: Optional[list[dict]] = None
    internal_notes: Optional[str] = None


class QuotePreparationCreate(SQLModel):
    id: Optional[str] = None
    customer_name: str = Field(min_length=1, max_length=200)
    customer_email: Optional[str] = Field(default=None, max_length=200)
    customer_phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = Field(default=None, max_length=500)
    task_type: Optional[str] = Field(default=None, max_length=200)
    short_summary: Optional[str] = None
    detailed_description: Optional[str] = None
    internal_notes: Optional[str] = None
