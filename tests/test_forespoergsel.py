"""Tests for public /forespoergsel endpoint (Phase 1).

No auth override — this is a public endpoint with company_id as query-param.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from haandvaerker.main import app
from haandvaerker.database import get_session
from haandvaerker.models.company import Company
from haandvaerker.models.inbox_message import InboxMessage, InboxSource


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(name="session_pub")
def session_pub_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="active_company")
def active_company_fixture(session_pub: Session) -> Company:
    company = Company(id=str(uuid.uuid4()), name="Offentlig Test Firma", active=True)
    session_pub.add(company)
    session_pub.commit()
    session_pub.refresh(company)
    return company


@pytest.fixture(name="inactive_company")
def inactive_company_fixture(session_pub: Session) -> Company:
    company = Company(id=str(uuid.uuid4()), name="Inaktivt Firma", active=False)
    session_pub.add(company)
    session_pub.commit()
    session_pub.refresh(company)
    return company


@pytest.fixture(name="pub_client")
def pub_client_fixture(session_pub: Session):
    """Public client: only session override, no company_context override."""
    def override_get_session():
        yield session_pub

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _post_form(client: TestClient, company_id: str, **extra) -> object:
    payload = {
        "sender_name": "Per Testesen",
        "sender_email": "per@example.com",
        "sender_phone": "12345678",
        "subject": "Malerforespørgsel",
        "body": "Hej, jeg søger en maler til min villa.",
        **extra,
    }
    return client.post(f"/forespoergsel?company_id={company_id}", json=payload)


# ── AC-1: Valid active company → 201, received=true, InboxMessage created ─────

def test_valid_company_creates_inbox_message(
    pub_client: TestClient, active_company: Company, session_pub: Session
):
    r = _post_form(pub_client, active_company.id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["received"] is True
    assert "acknowledged" in body

    # Verify InboxMessage exists with source=website
    from sqlmodel import select
    msgs = session_pub.exec(
        select(InboxMessage).where(InboxMessage.company_id == active_company.id)
    ).all()
    assert len(msgs) == 1
    assert msgs[0].source == InboxSource.website


# ── AC-2: Response never contains company_id or internal IDs ─────────────────

def test_response_does_not_leak_ids(
    pub_client: TestClient, active_company: Company
):
    r = _post_form(pub_client, active_company.id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert "company_id" not in body
    assert "id" not in body


# ── AC-3: Unknown company_id → same generic error (no info leakage) ───────────

def test_unknown_company_id_same_error_as_inactive(
    pub_client: TestClient, inactive_company: Company
):
    unknown_id = str(uuid.uuid4())
    r_unknown = _post_form(pub_client, unknown_id)
    r_inactive = _post_form(pub_client, inactive_company.id)

    assert r_unknown.status_code == r_inactive.status_code
    # Both must fail with the same status (not 201)
    assert r_unknown.status_code != 201

    # The error bodies must be identical text (no extra detail for one or the other)
    assert r_unknown.json()["detail"] == r_inactive.json()["detail"]


# ── AC-4: POST without company_id → 422 ──────────────────────────────────────

def test_missing_company_id_returns_422(pub_client: TestClient):
    r = pub_client.post("/forespoergsel", json={
        "sender_name": "Test",
        "sender_email": "test@example.com",
        "subject": "Test",
        "body": "Test",
    })
    assert r.status_code == 422


# ── AC-5: SMTP not configured → still 201, acknowledged=false ────────────────

def test_smtp_not_configured_still_creates_message(
    pub_client: TestClient, active_company: Company
):
    # Patch send_acknowledgement_email to simulate SMTP not configured
    with patch(
        "haandvaerker.services.inbox_ingest.send_acknowledgement_email",
        return_value={"sent": False, "error": "SMTP ikke konfigureret"},
    ):
        r = _post_form(pub_client, active_company.id)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["received"] is True
    assert body["acknowledged"] is False


# ── AC-6: GET /forespoergsel → 200 text/html ─────────────────────────────────

def test_get_forespoergsel_serves_html(pub_client: TestClient):
    r = pub_client.get("/forespoergsel")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


# ── AC-7: Auto-send raises → InboxMessage created, processing_error filled ───

def test_send_failure_message_still_created_processing_error_set(
    pub_client: TestClient, active_company: Company, session_pub: Session
):
    with patch(
        "haandvaerker.services.inbox_ingest.send_acknowledgement_email",
        side_effect=RuntimeError("SMTP exploded"),
    ):
        r = _post_form(pub_client, active_company.id)

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["received"] is True
    assert body["acknowledged"] is False

    # InboxMessage must exist and processing_error must be set
    from sqlmodel import select
    msgs = session_pub.exec(
        select(InboxMessage).where(InboxMessage.company_id == active_company.id)
    ).all()
    assert len(msgs) == 1
    assert msgs[0].processing_error is not None
    assert len(msgs[0].processing_error) > 0


# ── AC-8: Retry endpoint clears processing_error on success ──────────────────

def test_retry_clears_processing_error(
    session_pub: Session, active_company: Company
):
    """A message with processing_error can be replayed; on success it is cleared."""
    from datetime import datetime

    # Create a message with a processing_error via the authenticated (session) override
    def override_get_session():
        yield session_pub

    from haandvaerker.dependencies import get_company_context, CompanyContext

    def override_ctx():
        return CompanyContext(session=session_pub, company_id=active_company.id)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_company_context] = override_ctx

    try:
        with TestClient(app) as c:
            msg = InboxMessage(
                id=str(uuid.uuid4()),
                company_id=active_company.id,
                received_at=datetime.utcnow(),
                source=InboxSource.website,
                sender_name="Retry Test",
                sender_email="retry@example.com",
                subject="Retry",
                body="Prøv igen",
                processing_error="SMTP exploded",
            )
            session_pub.add(msg)
            session_pub.commit()
            session_pub.refresh(msg)

            # Mock send to succeed this time
            with patch(
                "haandvaerker.services.inbox_ingest.send_acknowledgement_email",
                return_value={"sent": True, "error": None},
            ):
                r = c.post(f"/inbox/{msg.id}/retry")

            assert r.status_code == 200, r.text
            session_pub.refresh(msg)
            assert msg.processing_error is None
    finally:
        app.dependency_overrides.clear()


# ── AC-9: invoice_payment never silently archived — visual flag in markup ─────

def test_invoice_payment_flag_in_inbox_card_html():
    """Invoice-payment classification data-id must render with a red badge."""
    # We test the HTML static content for the attribute that signals invoice_payment
    import pathlib
    ui_html = (
        pathlib.Path(__file__).parent.parent
        / "src" / "haandvaerker" / "static" / "ui.html"
    ).read_text(encoding="utf-8")
    # The inboxCardHtml function must reference invoice_payment visual differentiation
    assert "invoice_payment" in ui_html
    # The processing_error retry button must also be present in the markup function
    assert "processing_error" in ui_html or "retry" in ui_html.lower()


# ── AC-10: InboxMessageRead includes processing_error field ──────────────────

def test_inbox_message_read_has_processing_error_field(
    pub_client: TestClient, active_company: Company, session_pub: Session
):
    """After creating, the InboxMessage model exposes processing_error via authenticated inbox."""

    def override_get_session():
        yield session_pub

    from haandvaerker.dependencies import get_company_context, CompanyContext

    def override_ctx():
        return CompanyContext(session=session_pub, company_id=active_company.id)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_company_context] = override_ctx

    try:
        with TestClient(app) as c:
            r = _post_form(pub_client, active_company.id)
            assert r.status_code == 201, r.text

            msgs = c.get("/inbox/").json()
            assert len(msgs) == 1
            # processing_error field must be present (may be None)
            assert "processing_error" in msgs[0]
    finally:
        app.dependency_overrides.clear()
