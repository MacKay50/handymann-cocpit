import uuid
from datetime import date
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class VatPeriodStatus(str, Enum):
    open = "open"
    locked = "locked"
    submitted = "submitted"


class VatPeriodCreate(SQLModel):
    id: Optional[str] = None
    period_start: date
    period_end: date
    notes: Optional[str] = None


class VatPeriod(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    period_start: date
    period_end: date
    status: VatPeriodStatus = Field(default=VatPeriodStatus.open)
    # Set on lock; None while open
    outgoing_vat: Optional[float] = None
    incoming_vat: Optional[float] = None
    net_vat: Optional[float] = None
    invoice_count: Optional[int] = None
    expense_count: Optional[int] = None
    notes: Optional[str] = None
    active: bool = Field(default=True)


class VatPeriodRead(SQLModel):
    id: str
    company_id: str
    period_start: date
    period_end: date
    status: VatPeriodStatus
    outgoing_vat: Optional[float]
    incoming_vat: Optional[float]
    net_vat: Optional[float]
    invoice_count: Optional[int]
    expense_count: Optional[int]
    notes: Optional[str]
    active: bool


class VatPreview(SQLModel):
    company_id: str
    period_start: date
    period_end: date
    outgoing_vat: float
    incoming_vat: float
    net_vat: float
    invoice_count: int
    expense_count: int


class VatExportInvoiceItem(SQLModel):
    id: str
    invoice_number: str
    issue_date: date
    customer_id: str
    subtotal: float
    vat_amount: float
    total: float
    status: str


class VatExportExpenseItem(SQLModel):
    id: str
    date: date
    category: str
    description: Optional[str]
    amount_excl_vat: float
    vat_amount: float
    amount_total: float


class VatExport(SQLModel):
    period_id: str
    company_id: str
    period_start: date
    period_end: date
    status: VatPeriodStatus
    outgoing_vat: float
    incoming_vat: float
    net_vat: float
    invoice_count: int
    expense_count: int
    invoices: list[VatExportInvoiceItem]
    expenses: list[VatExportExpenseItem]
