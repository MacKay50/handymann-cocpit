from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class InvoiceCaseStatus(str, Enum):
    received = "received"
    classified = "classified"
    not_relevant = "not_relevant"
    needs_review = "needs_review"
    payment_required = "payment_required"
    bank_opened = "bank_opened"
    handled = "handled"
    reconciliation_pending = "reconciliation_pending"
    payment_confirmed = "payment_confirmed"
    duplicate = "duplicate"
    reminder_received = "reminder_received"
    rejected = "rejected"
    archived = "archived"


class InvoicePriority(str, Enum):
    red = "red"
    orange = "orange"
    yellow = "yellow"
    green = "green"


class InvoiceCase(SQLModel, table=True):
    __tablename__ = "invoice_case"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    creditor_id: Optional[str] = Field(default=None, foreign_key="creditor.id")
    source_mail_message_id: Optional[str] = Field(default=None, foreign_key="mail_message.id")
    source_document_id: Optional[str] = Field(default=None, foreign_key="invoice_document.id")
    invoice_number: Optional[str] = Field(default=None, max_length=100)
    customer_number: Optional[str] = Field(default=None, max_length=100)
    amount_ore: int = Field(default=0)
    currency: str = Field(default="DKK", max_length=3)
    invoice_date: Optional[date] = Field(default=None)
    due_date: Optional[date] = Field(default=None)
    payment_reference: Optional[str] = Field(default=None, max_length=255)
    status: InvoiceCaseStatus = Field(default=InvoiceCaseStatus.received)
    priority: InvoicePriority = Field(default=InvoicePriority.yellow)
    confidence: float = Field(default=0.0)
    fingerprint: str = Field(max_length=64)
    is_reminder: bool = Field(default=False)
    reminder_level: Optional[int] = Field(default=None)
    creditor_name_raw: Optional[str] = Field(default=None, max_length=255)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
