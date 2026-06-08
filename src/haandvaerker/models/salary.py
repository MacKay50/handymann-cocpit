import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class SalaryStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    paid = "paid"
    cancelled = "cancelled"


def compute_salary_amounts(gross: float, tax_percentage: float) -> tuple[float, float]:
    """Returns (tax_amount, net_amount)."""
    q = Decimal("0.01")
    gross_d = Decimal(str(gross))
    rate = Decimal(str(tax_percentage)) / Decimal("100")
    tax = (gross_d * rate).quantize(q, ROUND_HALF_UP)
    net = (gross_d - tax).quantize(q, ROUND_HALF_UP)
    return float(tax), float(net)


class SalaryCreate(SQLModel):
    id: Optional[str] = None
    employee_id: str
    period_start: date
    period_end: date
    gross_amount: float = Field(gt=0)
    tax_percentage: float = Field(ge=0, le=100)
    payment_date: Optional[date] = None
    salary_ref: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class Salary(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    employee_id: str = Field(foreign_key="employee.id")
    period_start: date
    period_end: date
    gross_amount: float
    tax_percentage: float
    tax_amount: float
    net_amount: float
    payment_date: Optional[date] = None
    salary_ref: Optional[str] = None
    status: SalaryStatus = Field(default=SalaryStatus.draft)
    notes: Optional[str] = None
    active: bool = Field(default=True)


class SalaryRead(SQLModel):
    id: str
    company_id: str
    employee_id: str
    period_start: date
    period_end: date
    gross_amount: float
    tax_percentage: float
    tax_amount: float
    net_amount: float
    payment_date: Optional[date]
    salary_ref: Optional[str]
    status: SalaryStatus
    notes: Optional[str]
    active: bool


class SalaryUpdate(SQLModel):
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    gross_amount: Optional[float] = Field(default=None, gt=0)
    tax_percentage: Optional[float] = Field(default=None, ge=0, le=100)
    payment_date: Optional[date] = None
    salary_ref: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class SalarySummary(SQLModel):
    total_gross: float
    total_tax: float
    total_net: float
    count: int
