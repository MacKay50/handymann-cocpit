"""Phase 1 — InboxMessage → InvoiceCase routing tests.

Acceptance criteria covered:
  AC1  invoice_payment InboxMessage → exactly ONE InvoiceCase + InvoiceActionItem;
       InvoiceCase.source_inbox_message_id == msg.id
  AC2  Repeated ingest of the same InboxMessage does NOT create a second case
       (idempotency via source_inbox_message_id)
  AC3  new_quote_request message does NOT create an InvoiceCase (no regression)
  AC4  monitoring_service exposes ingest_from_inbox(session, inbox_message, company_id)
  AC5  ingest_sample delegates to ingest_from_inbox; no duplicated pipeline logic
  AC6  InvoiceCase.source_inbox_message_id column exists; idempotency check works
  AC7  pytest / ruff / mypy green (covered by running the suite)
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generator

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from haandvaerker.models.company import Company
from haandvaerker.models.inbox_message import InboxMessage, InboxSource
from haandvaerker.models.invoice_action_item import InvoiceActionItem
from haandvaerker.models.invoice_case import InvoiceCase
from haandvaerker.services import inbox_ingest
from haandvaerker.services.invoice_monitoring import monitoring_service


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(name="session_inv")
def session_inv_fixture() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="company_inv")
def company_inv_fixture(session_inv: Session) -> str:
    company = Company(id=str(uuid.uuid4()), name="Faktura Firma ApS")
    session_inv.add(company)
    session_inv.commit()
    session_inv.refresh(company)
    return company.id


def _make_invoice_msg(session: Session, company_id: str, msg_id: str | None = None) -> InboxMessage:
    """Create an InboxMessage that looks like an invoice_payment."""
    msg = InboxMessage(
        id=msg_id or str(uuid.uuid4()),
        company_id=company_id,
        received_at=datetime.utcnow(),
        source=InboxSource.email,
        sender_name="Leverandør A/S",
        sender_email="faktura@leverandoer.dk",
        subject="Faktura #9999 forfald 2026-07-01",
        body="Faktura nr. 9999. Beløb: 12.500 kr. Betalingsfrist: 01-07-2026.",
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


def _make_quote_msg(session: Session, company_id: str) -> InboxMessage:
    """Create an InboxMessage that looks like a new_quote_request."""
    msg = InboxMessage(
        id=str(uuid.uuid4()),
        company_id=company_id,
        received_at=datetime.utcnow(),
        source=InboxSource.email,
        sender_name="Kunde Hansen",
        sender_email="kunde@example.com",
        subject="Ønsker tilbud på maling",
        body="Vi vil gerne have et prisoverslag på maling af stue.",
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


# ── AC4: ingest_from_inbox is importable and callable ─────────────────────────

def test_ingest_from_inbox_is_exported():
    """AC4 — monitoring_service must expose ingest_from_inbox."""
    assert hasattr(monitoring_service, "ingest_from_inbox"), (
        "ingest_from_inbox not found in monitoring_service"
    )
    assert callable(monitoring_service.ingest_from_inbox)


# ── AC1: invoice_payment → ONE InvoiceCase + InvoiceActionItem ────────────────

def test_ingest_from_inbox_creates_case_and_action_item(
    session_inv: Session, company_inv: str
):
    """AC1 — ingest_from_inbox creates exactly one InvoiceCase and one InvoiceActionItem."""
    msg = _make_invoice_msg(session_inv, company_inv)

    result = monitoring_service.ingest_from_inbox(session_inv, msg, company_inv)
    session_inv.commit()

    # One InvoiceCase must exist
    cases = session_inv.exec(
        select(InvoiceCase).where(InvoiceCase.source_inbox_message_id == msg.id)
    ).all()
    assert len(cases) == 1, f"Expected 1 InvoiceCase, got {len(cases)}"
    case = cases[0]

    # source_inbox_message_id set correctly
    assert case.source_inbox_message_id == msg.id

    # company_id correct (multi-tenant)
    assert case.company_id == company_inv

    # One InvoiceActionItem linked to the case
    action_items = session_inv.exec(
        select(InvoiceActionItem).where(InvoiceActionItem.invoice_case_id == case.id)
    ).all()
    assert len(action_items) == 1, f"Expected 1 InvoiceActionItem, got {len(action_items)}"

    # Return value is the InvoiceCase
    assert result.id == case.id


# ── AC2: idempotency — same message ingested twice → no second case ───────────

def test_ingest_from_inbox_idempotent(session_inv: Session, company_inv: str):
    """AC2 — calling ingest_from_inbox twice on the same InboxMessage returns
    the existing case without creating a duplicate."""
    msg = _make_invoice_msg(session_inv, company_inv)

    first = monitoring_service.ingest_from_inbox(session_inv, msg, company_inv)
    session_inv.commit()

    second = monitoring_service.ingest_from_inbox(session_inv, msg, company_inv)
    session_inv.commit()

    # Same case returned
    assert first.id == second.id

    # Still exactly one InvoiceCase for this source message
    cases = session_inv.exec(
        select(InvoiceCase).where(InvoiceCase.source_inbox_message_id == msg.id)
    ).all()
    assert len(cases) == 1, f"Idempotency violated: {len(cases)} cases found"

    # Still exactly one InvoiceActionItem for this case
    action_items = session_inv.exec(
        select(InvoiceActionItem).where(InvoiceActionItem.invoice_case_id == first.id)
    ).all()
    assert len(action_items) == 1


# ── AC1/AC2 via inbox_ingest routing ─────────────────────────────────────────

def test_inbox_ingest_routes_invoice_payment_to_invoice_case(
    session_inv: Session, company_inv: str
):
    """AC1 (routing) — ingest_message with classify=True on an invoice_payment
    message creates an InvoiceCase via the routing in _run_secondary_classify."""
    msg = inbox_ingest.ingest_message(
        session=session_inv,
        company_id=company_inv,
        company_name="Faktura Firma ApS",
        source=InboxSource.email,
        sender_name="Leverandør A/S",
        sender_email="faktura@leverandoer.dk",
        subject="Faktura #9999 forfald 2026-07-01",
        body="Faktura nr. 9999. Beløb: 12.500 kr. Betalingsfrist: 01-07-2026.",
        classify=True,
    )
    session_inv.refresh(msg)

    cases = session_inv.exec(
        select(InvoiceCase).where(InvoiceCase.source_inbox_message_id == msg.id)
    ).all()
    assert len(cases) == 1, f"Expected 1 InvoiceCase after routing, got {len(cases)}"
    assert cases[0].source_inbox_message_id == msg.id
    assert cases[0].company_id == company_inv


def test_inbox_ingest_invoice_payment_idempotent_via_routing(
    session_inv: Session, company_inv: str
):
    """AC2 (routing) — ingest twice on same message does not create duplicate cases."""
    msg = inbox_ingest.ingest_message(
        session=session_inv,
        company_id=company_inv,
        company_name="Faktura Firma ApS",
        source=InboxSource.email,
        sender_name="Leverandør A/S",
        sender_email="faktura@leverandoer.dk",
        subject="Faktura #9999 forfald 2026-07-01",
        body="Faktura nr. 9999. Beløb: 12.500 kr. Betalingsfrist: 01-07-2026.",
        classify=True,
    )
    # Run secondary classify again directly (simulates double-processing)
    inbox_ingest._run_secondary_classify(session_inv, msg)

    cases = session_inv.exec(
        select(InvoiceCase).where(InvoiceCase.source_inbox_message_id == msg.id)
    ).all()
    assert len(cases) == 1, f"Idempotency via routing violated: {len(cases)} cases"


# ── AC3: new_quote_request does NOT create an InvoiceCase ─────────────────────

def test_new_quote_request_does_not_create_invoice_case(
    session_inv: Session, company_inv: str
):
    """AC3 — new_quote_request message must NOT produce an InvoiceCase."""
    msg = inbox_ingest.ingest_message(
        session=session_inv,
        company_id=company_inv,
        company_name="Faktura Firma ApS",
        source=InboxSource.email,
        sender_name="Kunde Hansen",
        sender_email="kunde@example.com",
        subject="Ønsker tilbud på maling af stue",
        body="Vi vil gerne have et prisoverslag på maling.",
        classify=True,
    )
    cases = session_inv.exec(
        select(InvoiceCase).where(InvoiceCase.source_inbox_message_id == msg.id)
    ).all()
    assert len(cases) == 0, (
        f"new_quote_request should NOT create InvoiceCase, got {len(cases)}"
    )


# ── AC1/AC2 via inbox_ingest — error in ingest_from_inbox does NOT crash ──────

def test_ingest_from_inbox_failure_does_not_crash_ingest_message(
    session_inv: Session, company_inv: str
):
    """Secondary step contract — if ingest_from_inbox raises, InboxMessage survives
    and processing_error is set (never raises to caller)."""
    from unittest.mock import patch

    with patch(
        "haandvaerker.services.inbox_ingest.ingest_from_inbox",
        side_effect=RuntimeError("Faktura pipeline brak"),
    ):
        msg = inbox_ingest.ingest_message(
            session=session_inv,
            company_id=company_inv,
            company_name="Faktura Firma ApS",
            source=InboxSource.email,
            sender_name="Leverandør A/S",
            sender_email="faktura@leverandoer.dk",
            subject="Faktura #9999",
            body="Faktura nr. 9999. Beløb: 12.500 kr.",
            classify=True,
        )

    assert msg.id is not None
    session_inv.refresh(msg)
    assert msg.processing_error is not None
    assert "Faktura pipeline brak" in msg.processing_error


# ── AC6: InvoiceCase.source_inbox_message_id field exists on model ────────────

def test_invoice_case_has_source_inbox_message_id_field():
    """AC6 — InvoiceCase model must declare source_inbox_message_id field."""
    fields = InvoiceCase.model_fields
    assert "source_inbox_message_id" in fields, (
        "InvoiceCase missing source_inbox_message_id field"
    )


# ── AC5: ingest_sample delegates to ingest_from_inbox (no logic duplication) ──

def test_ingest_sample_delegates_to_ingest_from_inbox(
    session_inv: Session, company_inv: str
):
    """AC5 — ingest_sample must call ingest_from_inbox internally; the pipeline
    logic must live in one place only."""
    from unittest.mock import patch, MagicMock
    from haandvaerker.models.invoice_case import InvoiceCase as IC

    # We patch ingest_from_inbox to verify ingest_sample calls it
    fake_case = MagicMock(spec=IC)
    fake_case.id = "fake-case-id"

    with patch.object(
        monitoring_service, "ingest_from_inbox", return_value=fake_case
    ) as mock_fn:
        monitoring_service.ingest_sample(
            session=session_inv,
            company_id=company_inv,
            subject="Faktura test",
            sender="test@example.com",
            body_text="Faktura 123. Beløb: 5.000 kr.",
        )

    assert mock_fn.called, "ingest_sample did not delegate to ingest_from_inbox"
