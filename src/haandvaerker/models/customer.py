from __future__ import annotations

import uuid
from typing import Optional
from sqlmodel import Field, SQLModel

# Allowed values for payment_rating — stored as plain string for SQLite compatibility
PAYMENT_RATINGS = ("good", "neutral", "bad")


class CustomerBase(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = Field(default=None, max_length=500)
    cvr_number: Optional[str] = Field(default=None, max_length=20)
    economic_customer_number: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None)
    # Payment behaviour tracking
    payment_rating: Optional[str] = Field(default=None, max_length=20)   # "good" | "neutral" | "bad"
    payment_comment: Optional[str] = Field(default=None)                  # free-text, e.g. "Betaler altid 30 dage for sent"
    work_again: bool = Field(default=True)                                 # False = we do NOT want more work from this customer


class Customer(CustomerBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    active: bool = Field(default=True)


class CustomerCreate(CustomerBase):
    id: Optional[str] = None


class CustomerRead(SQLModel):
    id: str
    company_id: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    cvr_masked: Optional[str]
    economic_customer_number: Optional[str]
    notes: Optional[str]
    active: bool
    payment_rating: Optional[str]
    payment_comment: Optional[str]
    work_again: bool

    @classmethod
    def from_orm_masked(cls, customer: Customer) -> "CustomerRead":
        cvr = customer.cvr_number
        masked = f"****{cvr[-4:]}" if cvr and len(cvr) >= 4 else None
        return cls(
            id=customer.id,
            company_id=customer.company_id,
            name=customer.name,
            email=customer.email,
            phone=customer.phone,
            address=customer.address,
            cvr_masked=masked,
            economic_customer_number=customer.economic_customer_number,
            notes=customer.notes,
            active=customer.active,
            payment_rating=customer.payment_rating,
            payment_comment=customer.payment_comment,
            work_again=customer.work_again if customer.work_again is not None else True,
        )


class CustomerUpdate(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    cvr_number: Optional[str] = None
    economic_customer_number: Optional[str] = None
    notes: Optional[str] = None
    active: Optional[bool] = None
    payment_rating: Optional[str] = None
    payment_comment: Optional[str] = None
    work_again: Optional[bool] = None
