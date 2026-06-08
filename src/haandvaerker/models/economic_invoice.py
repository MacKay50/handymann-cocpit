from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, Index, SQLModel


class EconomicInvoiceStatus(str, Enum):
    unmatched = "unmatched"
    matched = "matched"
    ignored = "ignored"


class EconomicInvoice(SQLModel, table=True):
    __table_args__ = (
        Index(
            "ix_economicinvoice_company_number",
            "company_id",
            "economic_invoice_number",
            unique=True,
        ),
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    economic_invoice_number: str = Field(max_length=50)
    customer_name: str = Field(max_length=200)
    net_amount_ore: int
    vat_amount_ore: int
    gross_amount_ore: int
    invoice_date: date
    due_date: date
    payment_date: Optional[date] = Field(default=None)
    status: EconomicInvoiceStatus = Field(default=EconomicInvoiceStatus.unmatched)
    linked_project_id: Optional[str] = Field(default=None, foreign_key="project.id")
    economic_customer_id: Optional[str] = Field(default=None, foreign_key="economiccustomer.id")
    invoice_id: Optional[str] = Field(
        default=None,
        foreign_key="invoice.id",
        # NOTE: SQLite FK enforcement is off. Manual link set in Phase 8.
    )
    imported_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = Field(default=True)


class EconomicInvoiceCreate(SQLModel):
    company_id: str
    economic_invoice_number: str = Field(max_length=50)
    customer_name: str = Field(max_length=200)
    net_amount_ore: int
    vat_amount_ore: int
    gross_amount_ore: int
    invoice_date: date
    due_date: date
    payment_date: Optional[date] = None
    linked_project_id: Optional[str] = None


class EconomicInvoiceRead(SQLModel):
    id: str
    company_id: str
    economic_invoice_number: str
    customer_name: str
    net_amount_ore: int
    vat_amount_ore: int
    gross_amount_ore: int
    invoice_date: date
    due_date: date
    payment_date: Optional[date]
    status: EconomicInvoiceStatus
    linked_project_id: Optional[str]
    economic_customer_id: Optional[str]
    invoice_id: Optional[str] = None
    imported_at: datetime
    active: bool
    is_overdue: bool

