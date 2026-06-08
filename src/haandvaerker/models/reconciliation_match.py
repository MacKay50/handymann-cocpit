from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class MatchType(str, Enum):
    auto_exact = "auto_exact"
    auto_ai = "auto_ai"
    auto_number = "auto_number"   # fakturanummer udtrukket fra bankbeskrivelse
    manual = "manual"


class ReconciliationMatch(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    bank_transaction_id: str = Field(foreign_key="banktransaction.id")
    economic_invoice_id: str = Field(foreign_key="economicinvoice.id")
    match_type: MatchType
    confidence: Optional[float] = Field(default=None)
    confirmed: bool = Field(default=False)
    matched_at: datetime = Field(default_factory=datetime.utcnow)
    matched_by: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)
    active: bool = Field(default=True)


class ReconciliationMatchCreate(SQLModel):
    bank_transaction_id: str
    economic_invoice_id: str
    match_type: MatchType
    confidence: Optional[float] = None
    confirmed: bool = False
    matched_by: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = Field(default=None, max_length=500)


class ReconciliationMatchRead(SQLModel):
    id: str
    bank_transaction_id: str
    economic_invoice_id: str
    match_type: MatchType
    confidence: Optional[float]
    confirmed: bool
    matched_at: datetime
    matched_by: Optional[str]
    notes: Optional[str]
    active: bool
