from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ExtractionEvidence(SQLModel, table=True):
    __tablename__ = "extraction_evidence"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    invoice_case_id: str = Field(foreign_key="invoice_case.id")
    field_name: str = Field(max_length=100)
    extracted_value: Optional[str] = Field(default=None, max_length=500)
    source_text: Optional[str] = Field(default=None, max_length=1000)
    confidence: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
