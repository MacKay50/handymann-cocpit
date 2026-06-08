import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel


class ContactPersonBase(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    title: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=200)
    contact_type: str = Field(default="other", max_length=20)
    # Values: customer_contact / employee / supplier / other
    customer_id: Optional[str] = Field(default=None, foreign_key="customer.id")
    project_id: Optional[str] = Field(default=None, foreign_key="project.id")
    tags: Optional[str] = Field(default=None, max_length=500)  # comma-separated
    comment: Optional[str] = Field(default=None)


class ContactPersonCreate(ContactPersonBase):
    pass
    # company_id comes from session, never from body


class ContactPerson(ContactPersonBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContactPersonRead(ContactPersonBase):
    id: str
    company_id: str
    active: bool = True
    created_at: datetime


class ContactPersonUpdate(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_type: Optional[str] = None
    customer_id: Optional[str] = None
    project_id: Optional[str] = None
    tags: Optional[str] = None
    comment: Optional[str] = None
    active: Optional[bool] = None
