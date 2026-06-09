from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class CompanyEmailConfig(SQLModel, table=True):
    company_id: str = Field(primary_key=True, foreign_key="company.id")
    imap_host: Optional[str] = None
    imap_port: int = Field(default=993)
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = Field(default=587)
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: bool = Field(default=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyEmailConfigRead(SQLModel):
    company_id: str
    imap_host: Optional[str]
    imap_port: int
    imap_user: Optional[str]
    imap_password_set: bool
    smtp_host: Optional[str]
    smtp_port: int
    smtp_user: Optional[str]
    smtp_password_set: bool
    smtp_from: Optional[str]
    smtp_use_tls: bool
    updated_at: datetime


class CompanyEmailConfigUpdate(SQLModel):
    imap_host: Optional[str] = None
    imap_port: Optional[int] = None
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: Optional[bool] = None


class CompanyAiConfig(SQLModel, table=True):
    company_id: str = Field(primary_key=True, foreign_key="company.id")
    endpoint: Optional[str] = None
    model: Optional[str] = None
    fallback_model: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyAiConfigRead(SQLModel):
    company_id: str
    endpoint: Optional[str]
    model: Optional[str]
    fallback_model: Optional[str]
    updated_at: datetime


class CompanyAiConfigUpdate(SQLModel):
    endpoint: Optional[str] = None
    model: Optional[str] = None
    fallback_model: Optional[str] = None


class CompanyPromptConfig(SQLModel, table=True):
    company_id: str = Field(primary_key=True, foreign_key="company.id")
    draft_system: Optional[str] = None
    draft_user: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyPromptConfigRead(SQLModel):
    company_id: str
    draft_system: Optional[str]
    draft_user: Optional[str]
    updated_at: Optional[datetime] = None


class CompanyPromptConfigUpdate(SQLModel):
    draft_system: Optional[str] = None
    draft_user: Optional[str] = None
