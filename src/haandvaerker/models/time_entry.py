import uuid
from datetime import date
from typing import Optional
from sqlmodel import Field, SQLModel


class TimeEntryCreate(SQLModel):
    id: Optional[str] = None
    project_id: str
    employee_id: str
    date: date
    hours: float = Field(gt=0)
    hourly_rate: Optional[float] = Field(default=None, gt=0)
    description: Optional[str] = Field(default=None, max_length=500)
    billable: bool = True
    action_item_id: Optional[str] = None


class TimeEntry(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    employee_id: str = Field(foreign_key="employee.id")
    company_id: str = Field(foreign_key="company.id")
    date: date
    hours: float
    hourly_rate: float
    description: Optional[str] = None
    total: float
    billable: bool = Field(default=True)
    invoice_id: Optional[str] = Field(default=None)
    action_item_id: Optional[str] = Field(
        default=None,
        foreign_key="actionitem.id",
        # NOTE: SQLite FK enforcement is off (no PRAGMA foreign_keys=ON).
        # ActionItem uses soft-delete only — validated at app layer in Phase 5.
    )
    active: bool = Field(default=True)


class TimeEntryRead(SQLModel):
    id: str
    company_id: str
    project_id: str
    employee_id: str
    date: date
    hours: float
    hourly_rate: float
    description: Optional[str]
    total: float
    billable: bool
    invoice_id: Optional[str]
    action_item_id: Optional[str] = None
    active: bool
    warning: Optional[str] = None


class TimeEntryUpdate(SQLModel):
    date: Optional[date] = None
    hours: Optional[float] = Field(default=None, gt=0)
    hourly_rate: Optional[float] = Field(default=None, gt=0)
    description: Optional[str] = None
    billable: Optional[bool] = None
    action_item_id: Optional[str] = None


class TimeEntrySummary(SQLModel):
    project_id: str
    total_hours: float
    total_cost: float
    billable_hours: float
    billable_cost: float


class TimeSummaryEntry(SQLModel):
    id: str
    date: date
    hours: float
    description: Optional[str]
    employee_id: str


class TimeSummaryGroup(SQLModel):
    action_item_id: Optional[str]
    label: str
    total_hours: float
    entries: list[TimeSummaryEntry]
