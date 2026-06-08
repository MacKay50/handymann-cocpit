from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class InvoiceDocumentType(str, Enum):
    invoice = "invoice"
    reminder = "reminder"
    credit_note = "credit_note"
    receipt = "receipt"
    payment_notice = "payment_notice"
    unknown = "unknown"


class OcrStatus(str, Enum):
    not_attempted = "not_attempted"
    completed = "completed"
    failed = "failed"
    not_needed = "not_needed"


class InvoiceDocument(SQLModel, table=True):
    __tablename__ = "invoice_document"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    mail_message_id: Optional[str] = Field(default=None, foreign_key="mail_message.id")
    filename: str = Field(default="", max_length=255)
    document_type: InvoiceDocumentType = Field(default=InvoiceDocumentType.unknown)
    text_content: Optional[str] = Field(default=None)
    ocr_status: OcrStatus = Field(default=OcrStatus.not_attempted)
    created_at: datetime = Field(default_factory=datetime.utcnow)
