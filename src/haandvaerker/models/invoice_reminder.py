from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel


class InvoiceReminder(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    invoice_id: str = Field(foreign_key="invoice.id", index=True)
    company_id: str = Field(foreign_key="company.id")
    customer_id: str          # denormalised — customer.id at send time
    level: int                # 1 | 2 | 3
    fee_ore: int = Field(default=0)
    method: str = Field(default="manual", max_length=20)   # "email" | "manual" | "failed"
    email_to: Optional[str] = Field(default=None, max_length=200)
    subject: str = Field(max_length=500)
    body_text: str
    error_detail: Optional[str] = Field(default=None)
    sent_by: Optional[str] = Field(default=None, max_length=200)
    triggered_by: str = Field(default="manual", max_length=20)
    # Values: 'manual' | 'auto'. Added for Phase 6 automatic reminder job.
    created_at: datetime = Field(default_factory=datetime.utcnow)


class InvoiceReminderRead(SQLModel):
    id: str
    invoice_id: str
    company_id: str
    customer_id: str
    level: int
    fee_ore: int
    method: str
    email_to: Optional[str]
    subject: str
    body_text: str
    error_detail: Optional[str]
    sent_by: Optional[str]
    triggered_by: str = "manual"
    created_at: datetime
