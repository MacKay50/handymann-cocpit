from __future__ import annotations

import uuid
from datetime import datetime
from sqlmodel import Field, SQLModel


class InboxAttachment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    inbox_message_id: str = Field(foreign_key="inboxmessage.id")
    filename: str  # original display name — NOT the stored path
    content_type: str
    size_bytes: int
    storage_path: str  # UUID-based path under static/uploads/attachments/
    created_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = Field(default=True)


class InboxAttachmentRead(SQLModel):
    id: str
    company_id: str
    inbox_message_id: str
    filename: str
    content_type: str
    size_bytes: int
    storage_path: str
    created_at: datetime
    active: bool
