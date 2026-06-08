import uuid
from datetime import date
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class PaymentMethod(str, Enum):
    cash = "cash"
    bank_transfer = "bank_transfer"
    mobilepay = "mobilepay"
    other = "other"


class PaymentCreate(SQLModel):
    id: Optional[str] = None
    invoice_id: str
    amount: float = Field(gt=0)
    payment_date: date
    method: PaymentMethod
    notes: Optional[str] = Field(default=None, max_length=500)


class Payment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    invoice_id: str = Field(foreign_key="invoice.id")
    company_id: str = Field(foreign_key="company.id")
    project_id: str = Field(foreign_key="project.id")
    amount: float
    payment_date: date
    method: PaymentMethod
    notes: Optional[str] = None
    active: bool = Field(default=True)


class PaymentRead(SQLModel):
    id: str
    invoice_id: str
    company_id: str
    project_id: str
    amount: float
    payment_date: date
    method: PaymentMethod
    notes: Optional[str]
    active: bool


class PaymentSummary(SQLModel):
    invoice_id: str
    invoice_total: float
    total_paid: float
    outstanding: float
    overpaid: float
