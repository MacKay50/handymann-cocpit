import uuid
from typing import Optional
from sqlmodel import Field, SQLModel


class CompanyCreate(SQLModel):
    id: Optional[str] = None
    name: str = Field(min_length=1, max_length=200)
    cvr_number: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=200)
    logo_ref: Optional[str] = Field(default=None, max_length=500)


class Company(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    cvr_number: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_ref: Optional[str] = None
    active: bool = Field(default=True)


class CompanyRead(SQLModel):
    id: str
    name: str
    cvr_masked: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    logo_url: Optional[str] = None
    active: bool

    @classmethod
    def from_orm_masked(cls, company: "Company") -> "CompanyRead":
        cvr = company.cvr_number
        masked = f"****{cvr[-4:]}" if cvr and len(cvr) >= 4 else None
        return cls(
            id=company.id,
            name=company.name,
            cvr_masked=masked,
            address=company.address,
            phone=company.phone,
            email=company.email,
            logo_url=company.logo_ref,
            active=company.active,
        )


class CompanyUpdate(SQLModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    cvr_number: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    logo_ref: Optional[str] = None
