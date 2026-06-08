from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from haandvaerker.models.bank_transaction import (
    BankTransaction,
    BankTransactionStatus,
)
from haandvaerker.models.economic_invoice import (
    EconomicInvoice,
    EconomicInvoiceStatus,
)
from haandvaerker.models.reconciliation_match import (
    MatchType,
    ReconciliationMatch,
)


def _make_bank_tx(
    company_id: str,
    import_hash: str = "hash001",
    amount_ore: int = 100000,
) -> BankTransaction:
    from datetime import date

    return BankTransaction(
        company_id=company_id,
        transaction_date=date(2026, 3, 14),
        description="Test transaktion",
        amount_ore=amount_ore,
        import_hash=import_hash,
        status=BankTransactionStatus.unmatched,
    )


def _make_economic_invoice(
    company_id: str,
    invoice_number: str = "INV-001",
) -> EconomicInvoice:
    from datetime import date

    return EconomicInvoice(
        company_id=company_id,
        economic_invoice_number=invoice_number,
        customer_name="Testkundens ApS",
        net_amount_ore=80000,
        vat_amount_ore=20000,
        gross_amount_ore=100000,
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        status=EconomicInvoiceStatus.unmatched,
    )


# ---------------------------------------------------------------------------
# Test 1: integer round-trip for amount_ore
# ---------------------------------------------------------------------------

def test_bank_transaction_amount_ore_round_trip(
    session: Session, company_id: str
) -> None:
    tx = _make_bank_tx(company_id, import_hash="roundtrip-hash", amount_ore=123456)
    session.add(tx)
    session.commit()
    session.refresh(tx)

    result = session.get(BankTransaction, tx.id)
    assert result is not None
    assert result.amount_ore == 123456
    assert type(result.amount_ore) is int


# ---------------------------------------------------------------------------
# Test 2: duplicate import_hash raises IntegrityError
# ---------------------------------------------------------------------------

def test_bank_transaction_duplicate_import_hash_raises(
    session: Session, company_id: str
) -> None:
    tx1 = _make_bank_tx(company_id, import_hash="abc123")
    session.add(tx1)
    session.commit()

    tx2 = _make_bank_tx(company_id, import_hash="abc123")
    session.add(tx2)

    with pytest.raises(IntegrityError):
        session.commit()


# ---------------------------------------------------------------------------
# Test 3: two ReconciliationMatch rows sharing the same bank_transaction_id
# ---------------------------------------------------------------------------

def test_reconciliation_match_many_to_many(
    session: Session, company_id: str
) -> None:
    # Create a project for EconomicInvoice linked_project_id (optional, so skip it)
    tx = _make_bank_tx(company_id, import_hash="manytomany-hash", amount_ore=200000)
    session.add(tx)

    inv1 = _make_economic_invoice(company_id, invoice_number="INV-M01")
    inv2 = _make_economic_invoice(company_id, invoice_number="INV-M02")
    session.add(inv1)
    session.add(inv2)
    session.commit()
    session.refresh(tx)
    session.refresh(inv1)
    session.refresh(inv2)

    match1 = ReconciliationMatch(
        bank_transaction_id=tx.id,
        economic_invoice_id=inv1.id,
        match_type=MatchType.manual,
        confirmed=True,
    )
    match2 = ReconciliationMatch(
        bank_transaction_id=tx.id,
        economic_invoice_id=inv2.id,
        match_type=MatchType.manual,
        confirmed=True,
    )
    session.add(match1)
    session.add(match2)
    # Must NOT raise IntegrityError — many-to-many is intentional (DP-2)
    session.commit()

    from sqlmodel import select

    results = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.bank_transaction_id == tx.id
        )
    ).all()
    assert len(results) == 2
