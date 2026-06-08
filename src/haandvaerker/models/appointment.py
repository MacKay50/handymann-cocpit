import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class AppointmentType(str, Enum):
    site_visit = "site_visit"
    meeting = "meeting"
    estimate = "estimate"
    other = "other"


class AppointmentStatus(str, Enum):
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"


class AppointmentCreate(SQLModel):
    id: Optional[str] = None
    customer_id: Optional[str] = None
    project_id: Optional[str] = None
    employee_id: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: datetime
    location: Optional[str] = Field(default=None, max_length=500)
    appointment_type: AppointmentType
    notes: Optional[str] = None


class Appointment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    customer_id: Optional[str] = None
    project_id: Optional[str] = Field(default=None, foreign_key="project.id")
    employee_id: Optional[str] = Field(default=None, foreign_key="employee.id")
    title: str
    description: Optional[str] = None
    start_datetime: datetime
    end_datetime: datetime
    location: Optional[str] = None
    appointment_type: AppointmentType
    status: AppointmentStatus = Field(default=AppointmentStatus.scheduled)
    notes: Optional[str] = None
    active: bool = Field(default=True)


class AppointmentRead(SQLModel):
    id: str
    company_id: str
    customer_id: Optional[str]
    project_id: Optional[str]
    employee_id: Optional[str]
    title: str
    description: Optional[str]
    start_datetime: datetime
    end_datetime: datetime
    location: Optional[str]
    appointment_type: AppointmentType
    status: AppointmentStatus
    notes: Optional[str]
    active: bool


class AppointmentUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    location: Optional[str] = Field(default=None, max_length=500)
    appointment_type: Optional[AppointmentType] = None
    employee_id: Optional[str] = None
    notes: Optional[str] = None
