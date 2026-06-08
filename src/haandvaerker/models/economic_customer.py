from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, Index, SQLModel


class EconomicCustomer(SQLModel, table=True):
    __table_args__ = (
        Index(
            "ix_economiccustomer_company_number",
            "company_id",
            "economic_customer_number",
            unique=True,
        ),
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    economic_customer_number: str = Field(max_length=20)
    name: str = Field(max_length=200)
    address: Optional[str] = Field(default=None, max_length=500)
    postal_code: Optional[str] = Field(default=None, max_length=10)
    city: Optional[str] = Field(default=None, max_length=100)
    cvr_number: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    imported_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = Field(default=True)
    linked_customer_id: Optional[str] = Field(default=None, foreign_key="customer.id")
    source: str = Field(default="csv", max_length=20)  # "csv" | "derived"


class EconomicCustomerCreate(SQLModel):
    company_id: str
    economic_customer_number: str = Field(max_length=20)
    name: str = Field(max_length=200)
    address: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    cvr_number: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class EconomicCustomerRead(SQLModel):
    id: str
    company_id: str
    economic_customer_number: str
    name: str
    address: Optional[str]
    postal_code: Optional[str]
    city: Optional[str]
    cvr_masked: Optional[str]  # vision §6: CVR never exposed in cleartext
    email: Optional[str]
    phone: Optional[str]
    imported_at: datetime
    active: bool
    linked_customer_id: Optional[str]
    source: str

    @classmethod
    def from_ec(cls, ec: "EconomicCustomer") -> "EconomicCustomerRead":
        cvr = ec.cvr_number
        masked = f"****{cvr[-4:]}" if cvr and len(cvr) >= 4 else None
        return cls(
            id=ec.id,
            company_id=ec.company_id,
            economic_customer_number=ec.economic_customer_number,
            name=ec.name,
            address=ec.address,
            postal_code=ec.postal_code,
            city=ec.city,
            cvr_masked=masked,
            email=ec.email,
            phone=ec.phone,
            imported_at=ec.imported_at,
            active=ec.active,
            linked_customer_id=ec.linked_customer_id,
            source=ec.source,
        )
