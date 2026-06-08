import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel

VAT_RATE = Decimal("0.25")


class InvoiceStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    paid = "paid"
    cancelled = "cancelled"


class InvoiceSequence(SQLModel, table=True):
    year: int = Field(primary_key=True)
    last_number: int = Field(default=0)


# ── Line item ────────────────────────────────────────────────────────────────

class InvoiceLineCreate(SQLModel):
    description: str = Field(min_length=1, max_length=500)
    unit: Optional[str] = Field(default=None, max_length=50)
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)


class InvoiceLine(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    invoice_id: str = Field(foreign_key="invoice.id")
    description: str
    unit: Optional[str] = None
    quantity: float
    unit_price: float
    line_total: float


class InvoiceLineRead(SQLModel):
    id: str
    description: str
    unit: Optional[str]
    quantity: float
    unit_price: float
    line_total: float


# ── Invoice header ────────────────────────────────────────────────────────────

class InvoiceCreate(SQLModel):
    id: Optional[str] = None
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    issue_date: date
    due_date: date
    notes: Optional[str] = None
    lines: list[InvoiceLineCreate] = []


class Invoice(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    project_id: str = Field(foreign_key="project.id")
    customer_id: str
    invoice_number: str = Field(index=True, sa_column_kwargs={"unique": True})
    title: str
    description: Optional[str] = None
    issue_date: date
    due_date: date
    notes: Optional[str] = None
    status: InvoiceStatus = Field(default=InvoiceStatus.draft)
    subtotal: float
    vat_amount: float
    total: float
    active: bool = Field(default=True)


class InvoiceRead(SQLModel):
    id: str
    company_id: str
    project_id: str
    customer_id: str
    invoice_number: str
    title: str
    description: Optional[str]
    issue_date: date
    due_date: date
    notes: Optional[str]
    status: InvoiceStatus
    subtotal: float
    vat_amount: float
    total: float
    active: bool
    lines: list[InvoiceLineRead] = []


class InvoiceUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None
    lines: Optional[list[InvoiceLineCreate]] = None


class InvoiceSummary(SQLModel):
    project_id: str
    total_invoiced: float
    total_paid: float
    outstanding: float


class InvoiceDraftFromProject(SQLModel):
    project_id: str
    issue_date: date
    due_date: date
    title: Optional[str] = None


# ── Calculation helpers ───────────────────────────────────────────────────────

def compute_line_total(quantity: float, unit_price: float) -> float:
    result = Decimal(str(quantity)) * Decimal(str(unit_price))
    return float(result.quantize(Decimal("0.01"), ROUND_HALF_UP))


def compute_invoice_totals(line_totals: list[float]) -> tuple[float, float, float]:
    q = Decimal("0.01")
    subtotal = sum(Decimal(str(t)) for t in line_totals)
    vat = (subtotal * VAT_RATE).quantize(q, ROUND_HALF_UP)
    total = subtotal + vat
    return float(subtotal), float(vat), float(total)
