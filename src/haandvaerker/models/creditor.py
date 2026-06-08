from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class CreditorRiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Creditor(SQLModel, table=True):
    __tablename__ = "creditor"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    name: str = Field(max_length=255)
    cvr_number: Optional[str] = Field(default=None, max_length=20)
    default_category: Optional[str] = Field(default=None, max_length=100)
    risk_level: CreditorRiskLevel = Field(default=CreditorRiskLevel.low)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CreditorAlias(SQLModel, table=True):
    __tablename__ = "creditor_alias"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    creditor_id: str = Field(foreign_key="creditor.id")
    alias: str = Field(max_length=255)
    source: str = Field(default="manual", max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CreditorRead(SQLModel):
    id: str
    company_id: str
    name: str
    cvr_number: Optional[str]
    default_category: Optional[str]
    risk_level: CreditorRiskLevel
    active: bool
    created_at: datetime
