import uuid
from datetime import date
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class DeadlineCategory(str, Enum):
    vat_report = "vat_report"
    salary_run = "salary_run"
    annual_accounts = "annual_accounts"
    corporate_tax = "corporate_tax"
    insurance = "insurance"
    other = "other"


class DeadlineStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    skipped = "skipped"


class AdminDeadlineBase(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    category: DeadlineCategory
    due_date: date
    notes: Optional[str] = Field(default=None)


class AdminDeadline(AdminDeadlineBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    status: DeadlineStatus = Field(default=DeadlineStatus.pending)
    active: bool = Field(default=True)


class AdminDeadlineCreate(AdminDeadlineBase):
    id: Optional[str] = None


class AdminDeadlineRead(SQLModel):
    id: str
    company_id: str
    title: str
    category: DeadlineCategory
    due_date: date
    status: DeadlineStatus
    notes: Optional[str]
    active: bool


class AdminDeadlineUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    due_date: Optional[date] = None
    notes: Optional[str] = None


class AdminDeadlineGenerateYear(SQLModel):
    year: int = Field(ge=2000, le=2100)
    categories: Optional[list[DeadlineCategory]] = None
