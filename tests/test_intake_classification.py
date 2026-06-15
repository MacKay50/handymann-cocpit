"""Phase 2: Classification pipeline tests.

Acceptance criteria covered:
  AC1  New InboxMessage via ANY entry point gets automatic MessageClassification
  AC2  new_quote_request → automatic Enquiry(status=new) created, msg.enquiry_id set
  AC3  spam and invoice_payment → NO auto-Enquiry created
  AC4  invoice_payment message still appears in inbox (not dropped)
  AC5  Repeated ingest of same message does NOT duplicate Enquiry or classification
  AC6  Manual POST /inbox/{id}/convert still works and uses create_enquiry_from_message
  AC7  IMAP poll does NOT call local AI synchronously (use_llm=False path, mock-verified)
  AC8  If classification raises → InboxMessage still created, processing_error filled
  AC9  pytest green (covered by running the suite)
"""
from __future__ import annotations

from datetime import datetime
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from haandvaerker.main import app
from haandvaerker.database import get_session
from haandvaerker.dependencies import get_company_context, CompanyContext
from haandvaerker.models.company import Company
from haandvaerker.models.enquiry import Enquiry, EnquiryStatus
from haandvaerker.models.inbox_message import InboxMessage, InboxSource
from haandvaerker.models.message_classification import (
    MessageClassification,
    MessageCategory,
)
from haandvaerker.services import inbox_ingest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(name="session_cls")
def session_cls_fixture() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="company_cls")
def company_cls_fixture(session_cls: Session) -> str:
    import uuid
    company = Company(id=str(uuid.uuid4()), name="Klassificeringsfirma ApS")
    session_cls.add(company)
    session_cls.commit()
    session_cls.refresh(company)
    return company.id


@pytest.fixture(name="client_cls")
def client_cls_fixture(session_cls: Session, company_cls: str) -> Generator[TestClient, None, None]:
    def override_session():
        yield session_cls

    def override_ctx():
        return CompanyContext(session=session_cls, company_id=company_cls)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_company_context] = override_ctx
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_msg(
    session: Session,
    company_id: str,
    subject: str = "Ønsker tilbud på maling",
    body: str = "Vi vil gerne have et prisoverslag.",
    source: InboxSource = InboxSource.email,
    sender_name: str = "Test Kunde",
    sender_email: str = "kunde@example.com",
) -> InboxMessage:
    """Create an InboxMessage directly in the session (bypasses API)."""
    import uuid
    msg = InboxMessage(
        id=str(uuid.uuid4()),
        company_id=company_id,
        received_at=datetime.utcnow(),
        source=source,
        sender_name=sender_name,
        sender_email=sender_email,
        subject=subject,
        body=body,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return msg


# ── AC1: ingest_message with classify=True creates MessageClassification ─────

def test_ingest_classify_creates_classification(session_cls: Session, company_cls: str):
    """AC1 — rule-based classification record persisted for every ingested message."""
    msg = inbox_ingest.ingest_message(
        session=session_cls,
        company_id=company_cls,
        company_name="TestFirma",
        source=InboxSource.email,
        sender_name="Lars",
        sender_email="lars@example.com",
        subject="Ønsker tilbud på maling",
        body="Vi vil gerne have et overslag.",
        classify=True,
    )
    cls_records = session_cls.exec(
        select(MessageClassification).where(
            MessageClassification.inbox_message_id == msg.id
        )
    ).all()
    assert len(cls_records) == 1
    assert cls_records[0].primary_category == MessageCategory.new_quote_request


# ── AC2: new_quote_request → auto-Enquiry ─────────────────────────────────────

def test_new_quote_request_creates_enquiry(session_cls: Session, company_cls: str):
    """AC2 — new_quote_request auto-creates Enquiry; msg.enquiry_id set."""
    msg = inbox_ingest.ingest_message(
        session=session_cls,
        company_id=company_cls,
        company_name="TestFirma",
        source=InboxSource.email,
        sender_name="Peter Maler",
        sender_email="peter@example.com",
        sender_phone="12345678",
        subject="Ønsker tilbud på renovering",
        body="Jeg søger pris på maling af stue.",
        classify=True,
    )
    session_cls.refresh(msg)
    assert msg.enquiry_id is not None
    enquiry = session_cls.get(Enquiry, msg.enquiry_id)
    assert enquiry is not None
    assert enquiry.status == EnquiryStatus.new
    assert enquiry.company_id == company_cls
    assert enquiry.contact_name == "Peter Maler"
    assert enquiry.contact_email == "peter@example.com"
    assert enquiry.contact_phone == "12345678"


# ── AC2: source mapping from InboxSource to EnquirySource ─────────────────────

def test_enquiry_source_mapped_from_inbox_source(session_cls: Session, company_cls: str):
    """AC2 — EnquirySource is mapped correctly from InboxSource.website."""
    from haandvaerker.models.enquiry import EnquirySource
    msg = inbox_ingest.ingest_message(
        session=session_cls,
        company_id=company_cls,
        company_name="TestFirma",
        source=InboxSource.website,
        sender_name="Web Kunde",
        sender_email="web@example.com",
        subject="Ønsker tilbud",
        body="Pris på maling",
        classify=True,
    )
    session_cls.refresh(msg)
    enquiry = session_cls.get(Enquiry, msg.enquiry_id)
    assert enquiry is not None
    assert enquiry.source == EnquirySource.website


# ── AC2: title truncated to 200 chars ──────────────────────────────────────────

def test_enquiry_title_truncated_to_200(session_cls: Session, company_cls: str):
    """AC2 — Enquiry.title is the subject truncated to 200 chars."""
    long_subject = "A" * 300
    msg = inbox_ingest.ingest_message(
        session=session_cls,
        company_id=company_cls,
        company_name="TestFirma",
        source=InboxSource.email,
        sender_name="Kunde",
        sender_email="k@example.com",
        subject=long_subject,
        body="Tilbud på maling — pris ønsket.",
        classify=True,
    )
    session_cls.refresh(msg)
    enquiry = session_cls.get(Enquiry, msg.enquiry_id)
    assert enquiry is not None
    assert len(enquiry.title) == 200
    assert enquiry.title == long_subject[:200]


# ── AC3: spam → no Enquiry ────────────────────────────────────────────────────

def test_spam_no_enquiry(session_cls: Session, company_cls: str):
    """AC3 — spam classified messages do NOT produce an Enquiry."""
    msg = inbox_ingest.ingest_message(
        session=session_cls,
        company_id=company_cls,
        company_name="TestFirma",
        source=InboxSource.email,
        sender_name="Spammer",
        sender_email="spam@evil.com",
        subject="You are the winner! Lottery prize!",
        body="Congratulations! Click here to claim your casino prize.",
        classify=True,
    )
    session_cls.refresh(msg)
    assert msg.enquiry_id is None
    enquiries = session_cls.exec(
        select(Enquiry).where(Enquiry.company_id == company_cls)
    ).all()
    assert len(enquiries) == 0


# ── AC3: invoice_payment → no Enquiry ────────────────────────────────────────

def test_invoice_payment_no_enquiry(session_cls: Session, company_cls: str):
    """AC3 — invoice_payment does NOT produce an Enquiry."""
    msg = inbox_ingest.ingest_message(
        session=session_cls,
        company_id=company_cls,
        company_name="TestFirma",
        source=InboxSource.email,
        sender_name="Regning",
        sender_email="regning@example.com",
        subject="Faktura #1234",
        body="Betaling af faktura er modtaget. Kvittering vedhæftet.",
        classify=True,
    )
    session_cls.refresh(msg)
    assert msg.enquiry_id is None
    enquiries = session_cls.exec(
        select(Enquiry).where(Enquiry.company_id == company_cls)
    ).all()
    assert len(enquiries) == 0


# ── AC4: invoice_payment message still present in inbox ───────────────────────

def test_invoice_payment_stays_in_inbox(session_cls: Session, company_cls: str):
    """AC4 — invoice_payment message is persisted in the inbox (not dropped)."""
    msg = inbox_ingest.ingest_message(
        session=session_cls,
        company_id=company_cls,
        company_name="TestFirma",
        source=InboxSource.email,
        sender_name="Regning",
        sender_email="regning@example.com",
        subject="Faktura #1234",
        body="Betaling af faktura er modtaget.",
        classify=True,
    )
    session_cls.refresh(msg)
    found = session_cls.get(InboxMessage, msg.id)
    assert found is not None
    assert found.active is True


# ── AC5: idempotency — no duplicate classification or Enquiry ─────────────────

def test_classify_idempotent_no_duplicate(session_cls: Session, company_cls: str):
    """AC5 — calling ingest twice on same msg must not duplicate classification."""
    # First ingest creates the message
    msg = inbox_ingest.ingest_message(
        session=session_cls,
        company_id=company_cls,
        company_name="TestFirma",
        source=InboxSource.email,
        sender_name="Kunde",
        sender_email="kunde@example.com",
        subject="Tilbud på maling",
        body="Prisoverslag ønsket.",
        classify=True,
    )
    # Simulate calling classification again directly on the same message
    inbox_ingest._run_secondary_classify(session_cls, msg)

    cls_records = session_cls.exec(
        select(MessageClassification).where(
            MessageClassification.inbox_message_id == msg.id
        )
    ).all()
    assert len(cls_records) == 1

    enquiries = session_cls.exec(
        select(Enquiry).where(Enquiry.company_id == company_cls)
    ).all()
    assert len(enquiries) == 1


# ── AC5: full ingest twice on separate message objects is idempotent re: Enquiry ─

def test_enquiry_not_created_if_already_has_enquiry_id(session_cls: Session, company_cls: str):
    """AC5 — if msg already has enquiry_id, no second Enquiry is created."""
    import uuid
    # Manually create message with an existing enquiry_id
    existing_enquiry = Enquiry(
        id=str(uuid.uuid4()),
        company_id=company_cls,
        title="Eksisterende",
        source="email",
        status=EnquiryStatus.new,
    )
    session_cls.add(existing_enquiry)
    session_cls.commit()

    msg = InboxMessage(
        id=str(uuid.uuid4()),
        company_id=company_cls,
        received_at=datetime.utcnow(),
        source=InboxSource.email,
        sender_name="Kunde",
        sender_email="k@example.com",
        subject="Ønsker tilbud på maling",
        body="Pris",
        enquiry_id=existing_enquiry.id,
    )
    session_cls.add(msg)
    session_cls.commit()
    session_cls.refresh(msg)

    inbox_ingest._run_secondary_classify(session_cls, msg)

    enquiries = session_cls.exec(
        select(Enquiry).where(Enquiry.company_id == company_cls)
    ).all()
    assert len(enquiries) == 1  # no second one created


# ── AC6: manual /convert still works and uses create_enquiry_from_message ─────

def test_manual_convert_endpoint_still_works(client_cls: TestClient, company_cls: str):
    """AC6 — manual POST /inbox/{id}/convert returns 201 Enquiry."""
    r = client_cls.post("/inbox/", json={
        "source": "phone",
        "received_at": "2026-05-20T10:00:00",
        "sender_name": "Manuel Kunde",
        "sender_email": "manuel@example.com",
        "subject": "Manuel forespørgsel",
    })
    assert r.status_code == 201, r.json()
    msg = r.json()

    r2 = client_cls.post(f"/inbox/{msg['id']}/convert", json={"title": "Manuel Enquiry"})
    assert r2.status_code == 201
    enquiry = r2.json()
    assert enquiry["status"] == "new"
    assert enquiry["contact_name"] == "Manuel Kunde"
    assert enquiry["company_id"] == company_cls


def test_manual_convert_uses_shared_function(session_cls: Session, company_cls: str):
    """AC6 — create_enquiry_from_message is importable and produces correct Enquiry."""
    from haandvaerker.api.inbox import create_enquiry_from_message

    msg = _make_msg(session_cls, company_cls)
    enq = create_enquiry_from_message(session_cls, msg, company_cls)
    assert enq.company_id == company_cls
    assert enq.status == EnquiryStatus.new
    assert enq.contact_email == msg.sender_email


# ── AC7: IMAP poll uses use_llm=False ────────────────────────────────────────

def test_poll_inbox_calls_ingest_with_use_llm_false(session_cls: Session, company_cls: str):
    """AC7 — poll_inbox passes use_llm=False to ingest_message for each email."""
    from haandvaerker.email_poller import poll_inbox
    from haandvaerker.services.config_resolver import EmailConfig

    cfg = EmailConfig(
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="user@example.com",
        imap_password="secret",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="secret",
        smtp_from="user@example.com",
        smtp_use_tls=True,
    )

    # Build a minimal fake IMAP4_SSL object
    fake_imap = MagicMock()
    fake_imap.login.return_value = ("OK", [])
    fake_imap.select.return_value = ("OK", [b"1"])
    fake_imap.search.return_value = ("OK", [b"1"])
    fake_imap.fetch.return_value = (
        "OK",
        [(b"1 (RFC822 {100})", _make_raw_email())],
    )
    fake_imap.store.return_value = ("OK", [])

    with patch("haandvaerker.email_poller.imaplib.IMAP4_SSL", return_value=fake_imap):
        with patch("haandvaerker.email_poller.ingest_message") as mock_ingest:
            mock_msg = MagicMock()
            mock_msg.id = "fake-id"
            mock_ingest.return_value = mock_msg
            poll_inbox(company_cls, session_cls, cfg)

    # Verify use_llm=False and classify=True were passed
    assert mock_ingest.called
    _, kwargs = mock_ingest.call_args
    assert kwargs.get("classify") is True
    assert kwargs.get("use_llm") is False


def _make_raw_email() -> bytes:
    """Minimal RFC822 email bytes for testing."""
    return (
        b"From: sender@example.com\r\n"
        b"Subject: Tilbud onsket\r\n"
        b"Date: Tue, 20 May 2025 09:00:00 +0000\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"\r\n"
        b"Vi onsker pris pa maling.\r\n"
    )


# ── AC8: classification failure → InboxMessage still created, error logged ────

def test_classify_exception_stored_in_processing_error(session_cls: Session, company_cls: str):
    """AC8 — if classify_message raises, InboxMessage is created and error is recorded."""
    with patch(
        "haandvaerker.services.inbox_ingest.classify_message",
        side_effect=RuntimeError("Klassificering fejlede!"),
    ):
        msg = inbox_ingest.ingest_message(
            session=session_cls,
            company_id=company_cls,
            company_name="TestFirma",
            source=InboxSource.email,
            sender_name="Kunde",
            sender_email="k@example.com",
            subject="Tilbud",
            body="Pris",
            classify=True,
        )

    assert msg.id is not None  # message was created
    session_cls.refresh(msg)
    assert msg.processing_error is not None
    assert "Klassificering fejlede!" in msg.processing_error


# ── AC1: forespoergsel endpoint triggers classification ──────────────────────

def test_forespoergsel_endpoint_classifies(client_cls: TestClient, session_cls: Session, company_cls: str):
    """AC1 — /forespoergsel path sets classify=True."""
    with patch("haandvaerker.api.forespoergsel.ingest_message") as mock_ingest:
        mock_msg = MagicMock()
        mock_msg.processing_error = None
        mock_ingest.return_value = mock_msg

        client_cls.post(
            f"/forespoergsel?company_id={company_cls}",
            json={
                "sender_name": "Web Bruger",
                "sender_email": "web@example.com",
                "subject": "Ønsker tilbud",
                "body": "Hej",
            },
        )

    assert mock_ingest.called, "ingest_message was not called"
    _, kwargs = mock_ingest.call_args
    assert kwargs.get("classify") is True


# ── AC1: intake endpoint (type=message) triggers classification ───────────────

def test_intake_message_classifies(client_cls: TestClient, session_cls: Session, company_cls: str):
    """AC1 — POST /intake type=message calls ingest_message with classify=True."""
    with patch("haandvaerker.api.intake.ingest_message") as mock_ingest:
        mock_msg = MagicMock()
        mock_msg.id = "fake-intake-id"
        mock_ingest.return_value = mock_msg

        r = client_cls.post("/intake/", json={
            "type": "message",
            "source": "phone",
            "sender_name": "Intake Kunde",
            "sender_email": "intake@example.com",
            "subject": "Forespørgsel",
            "body": "Hej",
        })
        assert r.status_code == 201, r.json()

    assert mock_ingest.called
    _, kwargs = mock_ingest.call_args
    assert kwargs.get("classify") is True
