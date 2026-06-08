from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class InvoiceActionItemStatus(str, Enum):
    open = "open"
    bank_opened = "bank_opened"
    handled = "handled"
    rejected = "rejected"
    duplicate = "duplicate"
    confirmed = "confirmed"


class InvoiceActionItem(SQLModel, table=True):
    __tablename__ = "invoice_action_item"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    invoice_case_id: str = Field(foreign_key="invoice_case.id")
    company_id: str = Field(foreign_key="company.id")
    status: InvoiceActionItemStatus = Field(default=InvoiceActionItemStatus.open)
    due_date: Optional[date] = Field(default=None)
    handled_by: Optional[str] = Field(default=None, max_length=255)
    handled_at: Optional[datetime] = Field(default=None)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
