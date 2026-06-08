import uuid
from datetime import date
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class ProjectStatus(str, Enum):
    draft = "draft"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class ProjectBase(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None)
    status: ProjectStatus = Field(default=ProjectStatus.draft)
    start_date: Optional[date] = Field(default=None)
    end_date: Optional[date] = Field(default=None)
    address: Optional[str] = Field(default=None, max_length=500)
    notes: Optional[str] = Field(default=None)


class Project(ProjectBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    customer_id: str = Field(foreign_key="customer.id")
    company_id: str = Field(foreign_key="company.id")
    enquiry_id: Optional[str] = Field(default=None)
    close_reason: Optional[str] = Field(default=None, max_length=1000)
    close_override: bool = Field(default=False)
    active: bool = Field(default=True)


class ProjectCreate(ProjectBase):
    id: Optional[str] = None
    customer_id: str


class ProjectRead(SQLModel):
    id: str
    company_id: str
    customer_id: str
    enquiry_id: Optional[str]
    title: str
    description: Optional[str]
    status: ProjectStatus
    start_date: Optional[date]
    end_date: Optional[date]
    address: Optional[str]
    notes: Optional[str]
    close_reason: Optional[str] = None
    close_override: bool = False
    active: bool


class ProjectUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    address: Optional[str] = None
    notes: Optional[str] = None
