"""Phase 3 — debit bank matcher + payment confirmation tests.

Acceptance criteria covered:
  AC1  Debit BankTransaction matching on EXACT amount + payment_reference + date
       within 7 days → confirm_payment called → status payment_confirmed
  AC2  Non-exact match (wrong payment_reference) NEVER auto-confirms →
       status NOT payment_confirmed
  AC3  No match → InvoiceCase unchanged
  AC4  confirm_payment has at least one production caller in the bridge
  AC5  POST /reconciliation/match-debit endpoint exists and returns correct shape
  AC6  404 when BankTransaction not found; 403 on company mismatch
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from haandvaerker.models.bank_transaction import BankTransaction, BankTransactionStatus
from haandvaerker.models.company import Company
from haandvaerker.models.invoice_case import InvoiceCase, InvoiceCaseStatus
from haandvaerker.models.invoice_event import InvoiceEvent, InvoiceEventType
from haandvaerker.services.invoice_monitoring import reconciliation_bridge
from haandvaerker.services.invoice_monitoring.reconciliation_bridge import (
    match_debit_transaction,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(name="session_pay")
def session_pay_fixture() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="company_pay")
def company_pay_fixture(session_pay: Session) -> str:
    company = Company(id=str(uuid.uuid4()), name="Betalings Firma ApS")
    session_pay.add(company)
    session_pay.commit()
    return company.id


def _make_case(
    session: Session,
    company_id: str,
    amount_ore: int = 10000,
    due_date: date | None = None,
    payment_reference: str | None = "REF-001",
    status: InvoiceCaseStatus = InvoiceCaseStatus.payment_required,
) -> InvoiceCase:
    case = InvoiceCase(
        company_id=company_id,
        amount_ore=amount_ore,
        due_date=due_date or date(2026, 6, 1),
        payment_reference=payment_reference,
        status=status,
        fingerprint=str(uuid.uuid4()),
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def _make_debit_tx(
    session: Session,
    company_id: str,
    amount_ore: int = -10000,
    transaction_date: date | None = None,
    bank_reference: str | None = "REF-001",
) -> BankTransaction:
    tx = BankTransaction(
        company_id=company_id,
        transaction_date=transaction_date or date(2026, 6, 1),
        description="Betaling faktura",
        amount_ore=amount_ore,
        bank_reference=bank_reference,
        import_hash=str(uuid.uuid4()),
        status=BankTransactionStatus.unmatched,
    )
    session.add(tx)
    session.commit()
    session.refresh(tx)
    return tx


# ── AC1: exact match → payment_confirmed ─────────────────────────────────────

def test_exact_match_confirms_payment(session_pay: Session, company_pay: str):
    """AC1 — debit tx matching on amount + bank_reference + date → payment_confirmed."""
    case = _make_case(session_pay, company_pay, amount_ore=10000, payment_reference="REF-001")
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-10000, bank_reference="REF-001")

    result = match_debit_transaction(session_pay, tx, company_pay)
    session_pay.commit()

    assert result.matched is True
    assert result.auto_confirmed is True
    assert result.case_id == case.id

    session_pay.refresh(case)
    assert case.status == InvoiceCaseStatus.payment_confirmed


def test_exact_match_emits_payment_confirmed_event(session_pay: Session, company_pay: str):
    """AC1 — exact match must produce a payment_confirmed audit event."""
    case = _make_case(session_pay, company_pay, amount_ore=5000, payment_reference="REF-X")
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-5000, bank_reference="REF-X")

    match_debit_transaction(session_pay, tx, company_pay)
    session_pay.commit()

    events = session_pay.exec(
        select(InvoiceEvent).where(
            InvoiceEvent.invoice_case_id == case.id,
            InvoiceEvent.event_type == InvoiceEventType.payment_confirmed,
        )
    ).all()
    assert len(events) == 1, f"Expected 1 payment_confirmed event, got {len(events)}"


def test_exact_match_date_within_7_days(session_pay: Session, company_pay: str):
    """AC1 — 7-day window: tx date 6 days after due_date still matches."""
    due = date(2026, 6, 1)
    case = _make_case(session_pay, company_pay, amount_ore=7500, due_date=due, payment_reference="REF-D")
    tx = _make_debit_tx(
        session_pay, company_pay,
        amount_ore=-7500,
        transaction_date=due + timedelta(days=6),
        bank_reference="REF-D",
    )

    result = match_debit_transaction(session_pay, tx, company_pay)
    session_pay.commit()

    assert result.matched is True
    session_pay.refresh(case)
    assert case.status == InvoiceCaseStatus.payment_confirmed


def test_exact_match_date_outside_7_days_no_confirm(session_pay: Session, company_pay: str):
    """AC1 boundary — tx date 8 days after due_date must NOT auto-confirm → reconciliation_pending."""
    due = date(2026, 6, 1)
    case = _make_case(session_pay, company_pay, amount_ore=7500, due_date=due, payment_reference="REF-E")
    tx = _make_debit_tx(
        session_pay, company_pay,
        amount_ore=-7500,
        transaction_date=due + timedelta(days=8),
        bank_reference="REF-E",
    )

    result = match_debit_transaction(session_pay, tx, company_pay)
    session_pay.commit()

    assert result.matched is False
    assert result.auto_confirmed is False
    assert result.needs_review is True
    session_pay.refresh(case)
    assert case.status == InvoiceCaseStatus.reconciliation_pending


# ── AC2: non-exact match never auto-confirms ──────────────────────────────────

def test_wrong_bank_reference_no_auto_confirm(session_pay: Session, company_pay: str):
    """AC2 — mismatched bank_reference → no auto-confirm, case marked reconciliation_pending."""
    case = _make_case(session_pay, company_pay, amount_ore=10000, payment_reference="REF-001")
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-10000, bank_reference="REF-WRONG")

    result = match_debit_transaction(session_pay, tx, company_pay)
    session_pay.commit()

    assert result.auto_confirmed is False
    assert result.needs_review is True
    session_pay.refresh(case)
    assert case.status == InvoiceCaseStatus.reconciliation_pending


def test_wrong_amount_no_auto_confirm(session_pay: Session, company_pay: str):
    """AC2 — wrong amount (amount matches but off by 1 øre) → no auto-confirm."""
    case = _make_case(session_pay, company_pay, amount_ore=10000, payment_reference="REF-A")
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-9999, bank_reference="REF-A")

    result = match_debit_transaction(session_pay, tx, company_pay)

    assert result.auto_confirmed is False
    session_pay.refresh(case)
    assert case.status != InvoiceCaseStatus.payment_confirmed


def test_case_has_reference_tx_has_none_no_auto_confirm(session_pay: Session, company_pay: str):
    """REL-02 — case has payment_reference, tx has None → partial match, no auto-confirm."""
    case = _make_case(session_pay, company_pay, amount_ore=10000, payment_reference="REF-KNOWN")
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-10000, bank_reference=None)

    result = match_debit_transaction(session_pay, tx, company_pay)
    session_pay.commit()

    assert result.auto_confirmed is False
    assert result.needs_review is True
    session_pay.refresh(case)
    assert case.status == InvoiceCaseStatus.reconciliation_pending


def test_amount_match_only_no_reference_skips_reference_check(session_pay: Session, company_pay: str):
    """AC1 edge — when BOTH case.payment_reference and bank_reference are None,
    reference criterion is skipped → amount+date match is sufficient."""
    case = _make_case(session_pay, company_pay, amount_ore=10000, payment_reference=None)
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-10000, bank_reference=None)

    result = match_debit_transaction(session_pay, tx, company_pay)
    session_pay.commit()

    assert result.matched is True
    assert result.auto_confirmed is True
    session_pay.refresh(case)
    assert case.status == InvoiceCaseStatus.payment_confirmed


# ── AC3: no match → case unchanged ───────────────────────────────────────────

def test_no_match_case_unchanged(session_pay: Session, company_pay: str):
    """AC3 — tx with no corresponding case → InvoiceCase status unchanged."""
    case = _make_case(session_pay, company_pay, amount_ore=10000, payment_reference="REF-001")
    # Completely different amount
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-99999, bank_reference="REF-001")

    result = match_debit_transaction(session_pay, tx, company_pay)

    assert result.matched is False
    assert result.auto_confirmed is False
    assert result.case_id is None
    session_pay.refresh(case)
    assert case.status == InvoiceCaseStatus.payment_required


def test_no_match_for_different_company(session_pay: Session, company_pay: str):
    """Multi-tenant: case in other company must NOT be matched."""
    other_company = Company(id=str(uuid.uuid4()), name="Andet Firma")
    session_pay.add(other_company)
    session_pay.commit()

    case = _make_case(session_pay, other_company.id, amount_ore=10000, payment_reference="REF-X")
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-10000, bank_reference="REF-X")

    result = match_debit_transaction(session_pay, tx, company_pay)

    assert result.matched is False
    session_pay.refresh(case)
    assert case.status != InvoiceCaseStatus.payment_confirmed


def test_credit_transaction_not_matched(session_pay: Session, company_pay: str):
    """match_debit_transaction must only process debit (negative) transactions."""
    case = _make_case(session_pay, company_pay, amount_ore=10000, payment_reference="REF-C")
    # Credit (positive) transaction — wrong direction
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=10000, bank_reference="REF-C")

    result = match_debit_transaction(session_pay, tx, company_pay)

    assert result.matched is False
    assert result.auto_confirmed is False
    session_pay.refresh(case)
    assert case.status != InvoiceCaseStatus.payment_confirmed


def test_terminal_status_case_not_matched(session_pay: Session, company_pay: str):
    """Cases in terminal statuses must NOT be auto-confirmed again."""
    _make_case(
        session_pay, company_pay, amount_ore=10000, payment_reference="REF-T",
        status=InvoiceCaseStatus.payment_confirmed,
    )
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-10000, bank_reference="REF-T")

    result = match_debit_transaction(session_pay, tx, company_pay)

    assert result.matched is False


def test_no_double_confirmation(session_pay: Session, company_pay: str):
    """Calling match_debit_transaction twice on same tx+case only fires once."""
    case = _make_case(session_pay, company_pay, amount_ore=10000, payment_reference="REF-DD")
    tx = _make_debit_tx(session_pay, company_pay, amount_ore=-10000, bank_reference="REF-DD")

    result1 = match_debit_transaction(session_pay, tx, company_pay)
    session_pay.commit()
    session_pay.refresh(case)

    # Now case is payment_confirmed; second call should not match
    result2 = match_debit_transaction(session_pay, tx, company_pay)

    assert result1.matched is True
    assert result2.matched is False  # terminal status excludes it


# ── AC4: confirm_payment has at least one production caller ──────────────────

def test_confirm_payment_has_production_caller():
    """AC4 — reconciliation_bridge.match_debit_transaction calls confirm_payment."""
    import inspect
    source = inspect.getsource(reconciliation_bridge)
    assert "confirm_payment" in source
    # match_debit_transaction must call confirm_payment (not just define it)
    fn_source = inspect.getsource(match_debit_transaction)
    assert "confirm_payment(" in fn_source


# ── AC5: POST /reconciliation/match-debit endpoint ───────────────────────────

@pytest.fixture(name="api_client_fixture")
def api_client_fixture() -> Generator[TestClient, None, None]:
    """TestClient wired to an in-memory SQLite DB with a seeded company session."""
    from itsdangerous import URLSafeSerializer
    from haandvaerker.config import settings
    from haandvaerker.database import get_session
    from haandvaerker.main import app

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def override_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    with Session(engine) as setup_session:
        company = Company(id="test-company-api", name="API Test Firma")
        setup_session.add(company)
        setup_session.commit()

    s = URLSafeSerializer(settings.secret_key, salt="company-session")
    cookie_value = s.dumps("test-company-api")

    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("haandvaerker_company", cookie_value)

    yield client, engine

    app.dependency_overrides.clear()


def test_match_debit_endpoint_exact_match(api_client_fixture):
    """AC5 — POST /reconciliation/match-debit returns matched=True on exact match."""
    client, engine = api_client_fixture

    with Session(engine) as session:
        case = InvoiceCase(
            company_id="test-company-api",
            amount_ore=15000,
            due_date=date(2026, 6, 1),
            payment_reference="EP-REF",
            status=InvoiceCaseStatus.payment_required,
            fingerprint=str(uuid.uuid4()),
        )
        session.add(case)
        tx = BankTransaction(
            company_id="test-company-api",
            transaction_date=date(2026, 6, 1),
            description="Betaling",
            amount_ore=-15000,
            bank_reference="EP-REF",
            import_hash=str(uuid.uuid4()),
        )
        session.add(tx)
        session.commit()
        tx_id = tx.id

    response = client.post(
        "/reconciliation/match-debit",
        json={"bank_transaction_id": tx_id},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["matched"] is True
    assert data["auto_confirmed"] is True
    assert data["case_id"] is not None


def test_match_debit_endpoint_no_match(api_client_fixture):
    """AC5 — POST /reconciliation/match-debit returns matched=False when no match."""
    client, engine = api_client_fixture

    with Session(engine) as session:
        tx = BankTransaction(
            company_id="test-company-api",
            transaction_date=date(2026, 6, 1),
            description="Ukendt betaling",
            amount_ore=-99999,
            bank_reference="NO-MATCH",
            import_hash=str(uuid.uuid4()),
        )
        session.add(tx)
        session.commit()
        tx_id = tx.id

    response = client.post(
        "/reconciliation/match-debit",
        json={"bank_transaction_id": tx_id},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["matched"] is False
    assert data["auto_confirmed"] is False
    assert data["case_id"] is None


# ── AC6: 404 / 403 error handling ────────────────────────────────────────────

def test_match_debit_endpoint_404_unknown_tx(api_client_fixture):
    """AC6 — unknown bank_transaction_id → 404."""
    client, _ = api_client_fixture
    response = client.post(
        "/reconciliation/match-debit",
        json={"bank_transaction_id": "does-not-exist"},
    )
    assert response.status_code == 404


def test_match_debit_endpoint_403_wrong_company(api_client_fixture):
    """AC6 — bank transaction belonging to a different company → 403."""
    client, engine = api_client_fixture

    with Session(engine) as session:
        other = Company(id=str(uuid.uuid4()), name="Andet Firma API")
        session.add(other)
        tx = BankTransaction(
            company_id=other.id,
            transaction_date=date(2026, 6, 1),
            description="Fremmed betaling",
            amount_ore=-5000,
            import_hash=str(uuid.uuid4()),
        )
        session.add(tx)
        session.commit()
        tx_id = tx.id

    response = client.post(
        "/reconciliation/match-debit",
        json={"bank_transaction_id": tx_id},
    )
    assert response.status_code == 403
