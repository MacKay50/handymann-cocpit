import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class ExpenseCategory(str, Enum):
    materialer = "materialer"
    transport_km = "transport_km"
    parkering = "parkering"
    andet = "andet"


DEFAULT_KM_RATE = Decimal("3.76")
VAT_RATE = Decimal("0.25")


def compute_expense_amounts(
    category: ExpenseCategory,
    km: Optional[float],
    km_rate: Optional[float],
    amount_excl_vat: Optional[float],
    apply_vat: Optional[bool],
) -> tuple[float, float, float, Optional[float], Optional[float]]:
    """Returns (amount_excl_vat, vat_amount, amount_total, resolved_km, resolved_km_rate)."""
    q = Decimal("0.01")

    if category == ExpenseCategory.transport_km:
        if km is None:
            raise ValueError("km is required for transport_km category")
        resolved_km = Decimal(str(km))
        resolved_rate = Decimal(str(km_rate)) if km_rate is not None else DEFAULT_KM_RATE
        excl = (resolved_km * resolved_rate).quantize(q, ROUND_HALF_UP)
        vat = Decimal("0")
        total = excl
        return (
            float(excl),
            float(vat),
            float(total),
            float(resolved_km),
            float(resolved_rate),
        )

    if amount_excl_vat is None:
        raise ValueError(f"amount_excl_vat is required for {category} category")
    excl = Decimal(str(amount_excl_vat))
    use_vat = apply_vat if apply_vat is not None else (category == ExpenseCategory.materialer)
    vat = (excl * VAT_RATE).quantize(q, ROUND_HALF_UP) if use_vat else Decimal("0")
    total = (excl + vat).quantize(q, ROUND_HALF_UP)
    return float(excl.quantize(q, ROUND_HALF_UP)), float(vat), float(total), None, None


class ExpenseCreate(SQLModel):
    id: Optional[str] = None
    project_id: str
    employee_id: str
    category: ExpenseCategory
    date: date
    description: Optional[str] = Field(default=None, max_length=500)
    receipt_ref: Optional[str] = Field(default=None, max_length=200)
    billable: bool = True
    km: Optional[float] = Field(default=None, gt=0)
    km_rate: Optional[float] = Field(default=None, gt=0)
    amount_excl_vat: Optional[float] = Field(default=None, ge=0)
    apply_vat: Optional[bool] = None


class Expense(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    employee_id: str = Field(foreign_key="employee.id")
    company_id: str = Field(foreign_key="company.id")
    category: ExpenseCategory
    date: date
    description: Optional[str] = None
    receipt_ref: Optional[str] = None
    billable: bool = Field(default=True)
    km: Optional[float] = None
    km_rate: Optional[float] = None
    amount_excl_vat: float
    vat_amount: float
    amount_total: float
    invoice_id: Optional[str] = Field(default=None)
    active: bool = Field(default=True)


class ExpenseRead(SQLModel):
    id: str
    company_id: str
    project_id: str
    employee_id: str
    category: ExpenseCategory
    date: date
    description: Optional[str]
    receipt_ref: Optional[str]
    billable: bool
    km: Optional[float]
    km_rate: Optional[float]
    amount_excl_vat: float
    vat_amount: float
    amount_total: float
    invoice_id: Optional[str]
    active: bool


class ExpenseUpdate(SQLModel):
    date: Optional[date] = None
    description: Optional[str] = Field(default=None, max_length=500)
    receipt_ref: Optional[str] = Field(default=None, max_length=200)
    billable: Optional[bool] = None


class ExpenseSummary(SQLModel):
    project_id: str
    total_expenses: float
    billable_expenses: float
    total_km: float
