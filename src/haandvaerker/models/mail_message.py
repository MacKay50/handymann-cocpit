from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class MailProcessingStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    failed = "failed"


class MailMessage(SQLModel, table=True):
    __tablename__ = "mail_message"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    provider_message_id: Optional[str] = Field(default=None, max_length=255)
    subject: str = Field(default="", max_length=500)
    sender: str = Field(default="", max_length=255)
    body_text: Optional[str] = Field(default=None)
    body_hash: Optional[str] = Field(default=None, max_length=64)
    processing_status: MailProcessingStatus = Field(default=MailProcessingStatus.pending)
    received_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
