import uuid
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class EnquiryStatus(str, Enum):
    new = "new"
    qualified = "qualified"
    converted = "converted"
    closed = "closed"


class EnquirySource(str, Enum):
    phone = "phone"
    email = "email"
    walk_in = "walk_in"
    referral = "referral"
    website = "website"
    other = "other"


class EnquiryBase(SQLModel):
    title: str = Field(min_length=1, max_length=200)
    source: EnquirySource
    contact_name: Optional[str] = Field(default=None, max_length=200)
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    contact_email: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None, max_length=500)
    work_type: Optional[str] = Field(default=None, max_length=200)
    timeframe: Optional[str] = Field(default=None, max_length=200)


class Enquiry(EnquiryBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    customer_id: Optional[str] = Field(default=None, foreign_key="customer.id")
    status: EnquiryStatus = Field(default=EnquiryStatus.new)
    project_id: Optional[str] = Field(default=None)
    active: bool = Field(default=True)


class EnquiryCreate(EnquiryBase):
    id: Optional[str] = None
    customer_id: Optional[str] = None


class EnquiryRead(SQLModel):
    id: str
    company_id: str
    customer_id: Optional[str]
    status: EnquiryStatus
    project_id: Optional[str]
    title: str
    source: EnquirySource
    contact_name: Optional[str]
    contact_phone: Optional[str]
    contact_email: Optional[str]
    notes: Optional[str]
    address: Optional[str] = None
    work_type: Optional[str] = None
    timeframe: Optional[str] = None
    active: bool


class EnquiryUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    source: Optional[EnquirySource] = None
    contact_name: Optional[str] = Field(default=None, max_length=200)
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    contact_email: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = None
    address: Optional[str] = None
    work_type: Optional[str] = None
    timeframe: Optional[str] = None
    customer_id: Optional[str] = None


class EnquiryConvert(SQLModel):
    customer_id: str
    project_title: str = Field(min_length=1, max_length=200)
