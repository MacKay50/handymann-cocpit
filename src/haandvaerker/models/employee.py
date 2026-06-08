import uuid
from datetime import date
from typing import Optional
from sqlmodel import Field, SQLModel


class EmployeeBase(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    role: Optional[str] = Field(default=None, max_length=100)
    default_hourly_rate: float = Field(gt=0)
    hired_date: Optional[date] = None
    cpr_number: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = None


class Employee(EmployeeBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    active: bool = Field(default=True)


class EmployeeCreate(EmployeeBase):
    id: Optional[str] = None


class EmployeeRead(SQLModel):
    id: str
    company_id: str
    name: str
    role: Optional[str]
    default_hourly_rate: float
    hired_date: Optional[date]
    cpr_masked: Optional[str]
    notes: Optional[str]
    active: bool

    @classmethod
    def from_orm_masked(cls, emp: Employee) -> "EmployeeRead":
        cpr = emp.cpr_number
        masked = f"****{cpr[-4:]}" if cpr and len(cpr) >= 4 else None
        return cls(
            id=emp.id,
            company_id=emp.company_id,
            name=emp.name,
            role=emp.role,
            default_hourly_rate=emp.default_hourly_rate,
            hired_date=emp.hired_date,
            cpr_masked=masked,
            notes=emp.notes,
            active=emp.active,
        )


class EmployeeUpdate(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    role: Optional[str] = None
    default_hourly_rate: Optional[float] = Field(default=None, gt=0)
    hired_date: Optional[date] = None
    cpr_number: Optional[str] = Field(default=None, max_length=20)
    notes: Optional[str] = None
