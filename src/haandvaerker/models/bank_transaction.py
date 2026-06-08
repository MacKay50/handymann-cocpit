from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class BankTransactionStatus(str, Enum):
    unmatched = "unmatched"
    matched = "matched"
    ignored = "ignored"


class BankTransaction(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: str = Field(foreign_key="company.id")
    transaction_date: date
    description: str = Field(max_length=500)
    amount_ore: int
    balance_ore: Optional[int] = Field(default=None)
    bank_reference: Optional[str] = Field(default=None, max_length=100)
    import_hash: str = Field(unique=True, max_length=64)
    status: BankTransactionStatus = Field(default=BankTransactionStatus.unmatched)
    imported_at: datetime = Field(default_factory=datetime.utcnow)
    active: bool = Field(default=True)


class BankTransactionCreate(SQLModel):
    company_id: str
    transaction_date: date
    description: str = Field(max_length=500)
    amount_ore: int
    balance_ore: Optional[int] = None
    bank_reference: Optional[str] = Field(default=None, max_length=100)
    import_hash: str = Field(max_length=64)
    status: BankTransactionStatus = BankTransactionStatus.unmatched


class BankTransactionRead(SQLModel):
    id: str
    company_id: str
    transaction_date: date
    description: str
    amount_ore: int
    balance_ore: Optional[int]
    bank_reference: Optional[str]
    import_hash: str
    status: BankTransactionStatus
    imported_at: datetime
    active: bool
    is_credit: bool

    @classmethod
    def from_orm(cls, obj: BankTransaction) -> BankTransactionRead:
        return cls(
            id=obj.id,
            company_id=obj.company_id,
            transaction_date=obj.transaction_date,
            description=obj.description,
            amount_ore=obj.amount_ore,
            balance_ore=obj.balance_ore,
            bank_reference=obj.bank_reference,
            import_hash=obj.import_hash,
            status=obj.status,
            imported_at=obj.imported_at,
            active=obj.active,
            is_credit=obj.amount_ore > 0,
        )
