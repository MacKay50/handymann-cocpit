"""Unit tests for reconciliation_service — deterministic and AI matchers.

TDD: these tests are written before the service implementation.
"""
from __future__ import annotations

import pytest
from datetime import date, timedelta
from sqlmodel import Session

from haandvaerker.models.bank_transaction import BankTransaction, BankTransactionStatus
from haandvaerker.models.economic_invoice import EconomicInvoice, EconomicInvoiceStatus
from haandvaerker.models.reconciliation_match import MatchType
from haandvaerker.services.reconciliation_service import (
    run_deterministic_matches,
    run_ai_residual_matches,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_tx(session: Session, company_id: str, amount_ore: int, days_offset: int = 0, import_hash: str | None = None) -> BankTransaction:
    tx = BankTransaction(
        company_id=company_id,
        transaction_date=date(2026, 4, 15) + timedelta(days=days_offset),
        description=f"TX {amount_ore}",
        amount_ore=amount_ore,
        import_hash=import_hash or f"hash-{amount_ore}-{days_offset}",
        status=BankTransactionStatus.unmatched,
    )
    session.add(tx)
    return tx


def _make_inv(session: Session, company_id: str, gross_amount_ore: int, due_date_offset: int = 0, inv_number: str | None = None) -> EconomicInvoice:
    inv = EconomicInvoice(
        company_id=company_id,
        economic_invoice_number=inv_number or f"INV-{gross_amount_ore}-{due_date_offset}",
        customer_name="Test Kunde",
        net_amount_ore=int(gross_amount_ore * 0.8),
        vat_amount_ore=int(gross_amount_ore * 0.2),
        gross_amount_ore=gross_amount_ore,
        invoice_date=date(2026, 4, 1),
        due_date=date(2026, 4, 15) + timedelta(days=due_date_offset),
        status=EconomicInvoiceStatus.unmatched,
    )
    session.add(inv)
    return inv


# ── deterministic tests ───────────────────────────────────────────────────────

def test_deterministic_exact_match(session: Session, company_id: str) -> None:
    """Exact amount + date on boundary → auto_exact confirmed match."""
    tx = _make_tx(session, company_id, 1000000)
    inv = _make_inv(session, company_id, 1000000, due_date_offset=0)
    session.commit()

    matches = run_deterministic_matches(session, company_id)
    session.commit()  # run_deterministic_matches docs: "caller commits"

    assert len(matches) == 1
    assert matches[0].match_type == MatchType.auto_exact
    assert matches[0].confirmed is True

    session.refresh(tx)
    assert tx.status == BankTransactionStatus.matched

    session.refresh(inv)
    assert inv.status == EconomicInvoiceStatus.matched


def test_deterministic_no_match_amount_mismatch(session: Session, company_id: str) -> None:
    """1 øre difference — exact int comparison, no match."""
    _make_tx(session, company_id, 1000000)
    _make_inv(session, company_id, 999900)
    session.commit()

    matches = run_deterministic_matches(session, company_id)

    assert len(matches) == 0


def test_deterministic_no_match_date_outside_window(session: Session, company_id: str) -> None:
    """Same amount but 9 days apart (outside ±7 day window) → no match."""
    _make_tx(session, company_id, 1000000)
    _make_inv(session, company_id, 1000000, due_date_offset=9)
    session.commit()

    matches = run_deterministic_matches(session, company_id)

    assert len(matches) == 0


def test_deterministic_matches_at_edge_of_window(session: Session, company_id: str) -> None:
    """Exactly 7 days difference — boundary is inclusive, must match."""
    _make_tx(session, company_id, 1000000)
    _make_inv(session, company_id, 1000000, due_date_offset=7)
    session.commit()

    matches = run_deterministic_matches(session, company_id)

    assert len(matches) == 1


def test_deterministic_no_double_match(session: Session, company_id: str) -> None:
    """Two transactions with same amount, one invoice — only one match, not double."""
    _make_tx(session, company_id, 1000000, import_hash="hash-a")
    _make_tx(session, company_id, 1000000, import_hash="hash-b")
    _make_inv(session, company_id, 1000000)
    session.commit()

    matches = run_deterministic_matches(session, company_id)

    assert len(matches) == 1


# ── AI branch tests ───────────────────────────────────────────────────────────

def test_ai_branch_produces_proposed_matches(session: Session, company_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AI returns a candidate → match created with confirmed=False."""
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.is_enabled",
        lambda: True,
    )
    # Different amounts so deterministic matcher skips them
    tx = _make_tx(session, company_id, 1000000)
    session.commit()
    tx_id = tx.id

    inv = _make_inv(session, company_id, 990000)
    session.commit()
    inv_id = inv.id

    ai_response = f'[{{"bank_transaction_id": "{tx_id}", "economic_invoice_id": "{inv_id}", "confidence": 0.85}}]'
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.chat_completion",
        lambda **kw: ai_response,
    )

    matches = run_ai_residual_matches(session, company_id)

    assert len(matches) == 1
    assert matches[0].match_type == MatchType.auto_ai
    assert matches[0].confirmed is False  # NEVER auto-confirmed
    assert matches[0].confidence == pytest.approx(0.85)


def test_ai_disabled_returns_empty(session: Session, company_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AI disabled → empty list, no exception."""
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.is_enabled",
        lambda: False,
    )
    _make_tx(session, company_id, 1000000)
    _make_inv(session, company_id, 1000000)
    session.commit()

    matches = run_ai_residual_matches(session, company_id)

    assert matches == []


def test_ai_returns_none_falls_back_gracefully(session: Session, company_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AI returns None (Ollama down) → empty list, no exception."""
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.is_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.chat_completion",
        lambda **kw: None,
    )
    _make_tx(session, company_id, 1000000)
    _make_inv(session, company_id, 1000000)
    session.commit()

    matches = run_ai_residual_matches(session, company_id)

    assert matches == []  # Graceful fallback, no exception raised


def test_ai_low_confidence_skipped(session: Session, company_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AI candidate below threshold → not added."""
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.is_enabled",
        lambda: True,
    )
    tx = _make_tx(session, company_id, 1000000)
    session.commit()
    tx_id = tx.id

    inv = _make_inv(session, company_id, 990000)
    session.commit()
    inv_id = inv.id

    ai_response = f'[{{"bank_transaction_id": "{tx_id}", "economic_invoice_id": "{inv_id}", "confidence": 0.4}}]'
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.chat_completion",
        lambda **kw: ai_response,
    )

    matches = run_ai_residual_matches(session, company_id)

    assert len(matches) == 0


def test_ai_invalid_json_falls_back_gracefully(session: Session, company_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """AI returns garbage JSON → empty list, no exception."""
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.is_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "haandvaerker.services.reconciliation_service.local_ai.chat_completion",
        lambda **kw: "not valid json at all",
    )
    _make_tx(session, company_id, 1000000)
    _make_inv(session, company_id, 990000)
    session.commit()

    matches = run_ai_residual_matches(session, company_id)

    assert matches == []
