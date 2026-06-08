from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class MessageCategory(str, Enum):
    new_quote_request = "new_quote_request"
    project_update = "project_update"
    schedule_change = "schedule_change"
    invoice_payment = "invoice_payment"
    complaint = "complaint"
    general_inquiry = "general_inquiry"
    spam = "spam"
    other = "other"


class ClassificationSource(str, Enum):
    rule_based = "rule_based"
    local_ai = "local_ai"
    manual = "manual"


class EntityType(str, Enum):
    address = "address"
    date = "date"
    time = "time"
    phone = "phone"
    email = "email"
    project_reference = "project_reference"
    person_name = "person_name"
    amount = "amount"
    other = "other"


class MessageClassification(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id", index=True)
    inbox_message_id: str = Field(foreign_key="inboxmessage.id", index=True)
    primary_category: MessageCategory = Field(default=MessageCategory.other)
    secondary_categories_json: Optional[str] = Field(default=None)
    is_quote_related: bool = Field(default=False)
    is_project_related: bool = Field(default=False)
    is_calendar_related: bool = Field(default=False)
    requires_action: bool = Field(default=False)
    priority: int = Field(default=0)
    confidence: Optional[float] = Field(default=None)
    classification_source: ClassificationSource = Field(
        default=ClassificationSource.rule_based
    )
    user_overridden: bool = Field(default=False)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class MessageEntity(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    classification_id: str = Field(
        foreign_key="messageclassification.id", index=True
    )
    entity_type: EntityType
    value: str
    normalized_value: Optional[str] = Field(default=None)
    confidence: Optional[float] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Read / Create / Update schemas ──────────────────────────────────────────

class MessageClassificationRead(SQLModel):
    id: str
    company_id: str
    inbox_message_id: str
    primary_category: MessageCategory
    secondary_categories: list[str] = []
    is_quote_related: bool
    is_project_related: bool
    is_calendar_related: bool
    requires_action: bool
    priority: int
    confidence: Optional[float]
    classification_source: ClassificationSource
    user_overridden: bool
    active: bool
    created_at: datetime
    updated_at: datetime
    entities: list["MessageEntityRead"] = []


class MessageClassificationUpdate(SQLModel):
    primary_category: Optional[MessageCategory] = None
    is_quote_related: Optional[bool] = None
    is_project_related: Optional[bool] = None
    is_calendar_related: Optional[bool] = None
    requires_action: Optional[bool] = None
    priority: Optional[int] = None


class MessageEntityRead(SQLModel):
    id: str
    classification_id: str
    entity_type: EntityType
    value: str
    normalized_value: Optional[str]
    confidence: Optional[float]
    created_at: datetime
