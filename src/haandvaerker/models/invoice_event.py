from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class InvoiceEventType(str, Enum):
    mail_received = "mail_received"
    document_attached = "document_attached"
    document_classified = "document_classified"
    invoice_fields_extracted = "invoice_fields_extracted"
    creditor_matched = "creditor_matched"
    invoice_case_created = "invoice_case_created"
    action_item_created = "action_item_created"
    bank_opened = "bank_opened"
    marked_handled = "marked_handled"
    reminder_received = "reminder_received"
    duplicate_detected = "duplicate_detected"
    field_corrected = "field_corrected"
    sent_to_reconciliation = "sent_to_reconciliation"
    payment_confirmed = "payment_confirmed"
    rejected = "rejected"
    archived = "archived"
    priority_raised = "priority_raised"


class InvoiceEvent(SQLModel, table=True):
    __tablename__ = "invoice_event"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    invoice_case_id: str = Field(foreign_key="invoice_case.id")
    event_type: InvoiceEventType
    actor_type: str = Field(default="system", max_length=20)  # system | user | reconciliation
    actor_id: Optional[str] = Field(default=None, max_length=255)
    payload: Optional[str] = Field(default=None)  # JSON string — append-only, never mutated
    created_at: datetime = Field(default_factory=datetime.utcnow)
