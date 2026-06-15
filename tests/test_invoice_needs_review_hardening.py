"""Phase 4 — needs_review hardening for risky invoice extractions.

Acceptance criteria covered:
  AC1a  ingest_sample with amount_ore=0 (payment-relevant) -> status needs_review
  AC1b  ingest_sample with amount_ore=0 (payment-relevant) -> priority red
  AC2   ingest_sample without due_date -> priority >= orange (not green)
  AC3   ingest_sample with normal amount and due_date -> status payment_required (regression)
  AC4   compute_priority(amount_ore=0, ...) raises ValueError (unit test)
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Generator

import pytest
from sqlmodel import Session, SQLModel, create_engine

from haandvaerker.models.company import Company
from haandvaerker.models.invoice_case import InvoiceCaseStatus, InvoicePriority
from haandvaerker.services.invoice_monitoring.monitoring_service import ingest_sample
from haandvaerker.services.invoice_monitoring.priority import compute_priority


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(name="session_nr")
def session_nr_fixture() -> Generator[Session, None, None]:
    from sqlmodel.pool import StaticPool
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="company_nr")
def company_nr_fixture(session_nr: Session) -> str:
    company = Company(id=str(uuid.uuid4()), name="NeedsReview Firma ApS")
    session_nr.add(company)
    session_nr.commit()
    session_nr.refresh(company)
    return company.id


# ── AC4: compute_priority raises ValueError for amount_ore==0 ─────────────────

def test_compute_priority_raises_for_zero_amount() -> None:
    """AC4 — compute_priority must raise ValueError when amount_ore==0."""
    future_date = date.today() + timedelta(days=30)
    with pytest.raises(ValueError, match="amount_ore"):
        compute_priority(
            due_date=future_date,
            is_reminder=False,
            creditor_id="cred-123",
            confidence=0.9,
            amount_ore=0,
        )


def test_compute_priority_raises_for_none_amount() -> None:
    """compute_priority with amount_ore=None (cast to int) must raise ValueError."""
    future_date = date.today() + timedelta(days=30)
    with pytest.raises((ValueError, TypeError)):
        # amount_ore is typed int; passing None simulates extraction failure
        compute_priority(
            due_date=future_date,
            is_reminder=False,
            creditor_id="cred-123",
            confidence=0.9,
            amount_ore=None,  # type: ignore[arg-type]
        )


# ── AC1a: amount_ore==0 -> status needs_review ───────────────────────────────

def test_zero_amount_ingested_as_needs_review_status(
    session_nr: Session, company_nr: str
) -> None:
    """AC1a — ingest_sample with amount_ore=0 must produce status needs_review."""
    future_date = date.today() + timedelta(days=30)
    result = ingest_sample(
        session=session_nr,
        company_id=company_nr,
        subject="Faktura #NR-001 betaling",
        sender="kreditor@example.dk",
        body_text="Faktura 001. Betal venligst. Forfald: 2026-07-15.",
        amount_ore=0,
        creditor_name="Kreditor ApS",
        due_date=future_date,
    )

    assert result.status == InvoiceCaseStatus.needs_review.value, (
        f"Expected needs_review, got {result.status!r}. "
        "amount_ore==0 must be escalated, not silently low-priority."
    )


# ── AC1b: amount_ore==0 -> priority red ──────────────────────────────────────

def test_zero_amount_ingested_as_red_priority(
    session_nr: Session, company_nr: str
) -> None:
    """AC1b — ingest_sample with amount_ore=0 must produce priority red."""
    future_date = date.today() + timedelta(days=30)
    result = ingest_sample(
        session=session_nr,
        company_id=company_nr,
        subject="Faktura #NR-002 betaling",
        sender="kreditor@example.dk",
        body_text="Faktura 002. Betal venligst. Forfald: 2026-07-16.",
        amount_ore=0,
        creditor_name="Anden Kreditor ApS",
        due_date=future_date,
    )

    assert result.priority == InvoicePriority.red.value, (
        f"Expected red priority, got {result.priority!r}. "
        "amount_ore==0 must force red priority — this is a data quality failure."
    )


# ── AC2: no due_date -> priority >= orange ────────────────────────────────────

def test_missing_due_date_is_orange_or_higher(
    session_nr: Session, company_nr: str
) -> None:
    """AC2 — ingest_sample without due_date must produce priority orange or red (not green/yellow)."""
    result = ingest_sample(
        session=session_nr,
        company_id=company_nr,
        subject="Faktura #NR-003 uden forfald",
        sender="kreditor@example.dk",
        body_text="Faktura 003. Betal venligst. Intet forfald angivet.",
        amount_ore=50_000,
        creditor_name="Tredjedels Kreditor ApS",
        due_date=None,
    )

    _priority_rank = {
        InvoicePriority.green.value: 0,
        InvoicePriority.yellow.value: 1,
        InvoicePriority.orange.value: 2,
        InvoicePriority.red.value: 3,
    }
    rank = _priority_rank.get(result.priority, -1)
    assert rank >= 2, (  # orange=2, red=3
        f"Expected priority >= orange, got {result.priority!r}. "
        "Missing due_date is an unknown-risk signal and must not produce green or yellow."
    )


# ── AC3: normal invoice -> status payment_required (regression) ───────────────

def test_normal_invoice_remains_payment_required(
    session_nr: Session, company_nr: str
) -> None:
    """AC3 — ingest_sample with valid amount and due_date must produce payment_required status."""
    future_date = date.today() + timedelta(days=30)
    result = ingest_sample(
        session=session_nr,
        company_id=company_nr,
        subject="Faktura #NR-004 normal",
        sender="kreditor@example.dk",
        body_text="Faktura 004. Beloeb 5.000 kr. Forfald: 2026-07-20.",
        amount_ore=500_000,
        creditor_name="Normal Kreditor ApS",
        due_date=future_date,
    )

    assert result.status == InvoiceCaseStatus.payment_required.value, (
        f"Expected payment_required, got {result.status!r}. "
        "Normal invoice with valid amount and due_date must not be escalated."
    )
