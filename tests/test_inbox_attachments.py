"""
Tests for Phase 3 — InboxAttachment upload, list, and IMAP extraction.

TDD: these tests are written first and must initially FAIL (model/endpoints
don't exist yet).  They are the contract.
"""
from __future__ import annotations

import email as stdlib_email
import email.mime.multipart
import email.mime.text
import email.mime.base
import email.encoders
import io
import pathlib
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from haandvaerker.models.inbox_attachment import InboxAttachment
from haandvaerker.models.inbox_message import InboxMessage, InboxSource


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _post_message(client: TestClient, **extra) -> dict:
    payload = {
        "source": "email",
        "received_at": "2026-05-20T09:00:00",
        "sender_name": "Lars Jensen",
        "sender_email": "lars@example.com",
        "subject": "Forespørgsel",
        "body": "Hej",
        **extra,
    }
    r = client.post("/inbox/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


def _make_pdf(size: int = 100) -> bytes:
    return b"%PDF-1.4 " + b"x" * size


def _upload(
    client: TestClient,
    message_id: str,
    filename: str,
    content: bytes,
    content_type: str = "application/pdf",
) -> TestClient:  # type: ignore[return-value]
    return client.post(  # type: ignore[return-value]
        f"/inbox/{message_id}/attachments",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


# ---------------------------------------------------------------------------
# AC-1  POST with allowed file → 201, UUID storage_path
# ---------------------------------------------------------------------------

def test_upload_allowed_file_returns_201(client: TestClient, tmp_path: pathlib.Path):
    """Uploading a PDF to a message creates attachment row, returns 201."""
    msg = _post_message(client)
    with patch(
        "haandvaerker.api.inbox.ATTACHMENTS_DIR",
        tmp_path,
    ):
        r = _upload(client, msg["id"], "invoice.pdf", _make_pdf())
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["filename"] == "invoice.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] > 0
    # storage_path must be UUID-based, not the original name
    assert "invoice.pdf" not in body["storage_path"]
    assert body["storage_path"].startswith("static/uploads/attachments/")
    assert body["active"] is True


def test_upload_creates_db_row(client: TestClient, session: Session, tmp_path: pathlib.Path):
    """DB row is created with correct company_id and inbox_message_id."""
    msg = _post_message(client)
    with patch("haandvaerker.api.inbox.ATTACHMENTS_DIR", tmp_path):
        r = _upload(client, msg["id"], "photo.jpg", b"JFIF" + b"x" * 50, "image/jpeg")
    assert r.status_code == 201, r.json()
    att_id = r.json()["id"]
    att = session.get(InboxAttachment, att_id)
    assert att is not None
    assert att.inbox_message_id == msg["id"]
    assert att.filename == "photo.jpg"


# ---------------------------------------------------------------------------
# AC-2  Disallowed file type → 422
# ---------------------------------------------------------------------------

def test_upload_disallowed_extension_returns_422(client: TestClient, tmp_path: pathlib.Path):
    msg = _post_message(client)
    with patch("haandvaerker.api.inbox.ATTACHMENTS_DIR", tmp_path):
        r = _upload(client, msg["id"], "malware.exe", b"MZ\x90\x00", "application/octet-stream")
    assert r.status_code == 422


def test_upload_disallowed_extension_php(client: TestClient, tmp_path: pathlib.Path):
    msg = _post_message(client)
    with patch("haandvaerker.api.inbox.ATTACHMENTS_DIR", tmp_path):
        r = _upload(client, msg["id"], "shell.php", b"<?php", "application/x-php")
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# AC-3  File over MAX_SIZE_BYTES → 422
# ---------------------------------------------------------------------------

def test_upload_oversized_file_returns_422(client: TestClient, tmp_path: pathlib.Path):
    msg = _post_message(client)
    big = b"x" * (10 * 1024 * 1024 + 1)  # 10 MB + 1 byte
    with patch("haandvaerker.api.inbox.ATTACHMENTS_DIR", tmp_path):
        r = _upload(client, msg["id"], "big.pdf", big)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# AC-4  Path-traversal guard — stored name is UUID, display name preserved
# ---------------------------------------------------------------------------

def test_stored_filename_is_uuid_not_original(
    client: TestClient, tmp_path: pathlib.Path, session: Session
):
    """Disk file uses UUID; 'filename' column stores the original display name."""
    msg = _post_message(client)
    original_name = "../../../etc/passwd.pdf"
    with patch("haandvaerker.api.inbox.ATTACHMENTS_DIR", tmp_path):
        r = _upload(client, msg["id"], original_name, _make_pdf())
    assert r.status_code == 201, r.json()
    body = r.json()
    # Display name preserved as-is
    assert body["filename"] == original_name
    # But storage path must NOT contain the original name
    stored_path = pathlib.Path(body["storage_path"])
    assert stored_path.name != original_name
    # The actual file on disk must NOT be named after the original
    disk_files = list(tmp_path.iterdir())
    assert len(disk_files) == 1
    assert disk_files[0].name != original_name
    assert ".." not in str(disk_files[0])


# ---------------------------------------------------------------------------
# AC-5  IMAP poll creates InboxMessage + linked InboxAttachment
# ---------------------------------------------------------------------------

def _build_email_with_attachment(pdf_data: bytes) -> bytes:
    """Construct a minimal multipart email with a PDF attachment."""
    msg = stdlib_email.mime.multipart.MIMEMultipart()
    msg["Subject"] = "Tilbud med bilag"
    msg["From"] = "sender@example.com"
    msg["Date"] = "Mon, 01 Jan 2026 10:00:00 +0000"
    msg.attach(stdlib_email.mime.text.MIMEText("Se vedhæftet.", "plain"))
    part = stdlib_email.mime.base.MIMEBase("application", "pdf")
    part.set_payload(pdf_data)
    stdlib_email.encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename="quote.pdf")
    msg.attach(part)
    return msg.as_bytes()


def _make_email_cfg():
    from haandvaerker.services.config_resolver import EmailConfig
    return EmailConfig(
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="user@example.com",
        imap_password="secret",  # noqa: S106  # test-only mock credentials
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="secret",  # noqa: S106  # test-only mock credentials
        smtp_from="user@example.com",
        smtp_use_tls=True,
    )


def test_imap_poll_saves_attachment(session: Session, company_id: str, tmp_path: pathlib.Path):
    """poll_inbox() with an attachment email creates InboxMessage and InboxAttachment."""
    from haandvaerker.email_poller import poll_inbox

    cfg = _make_email_cfg()

    raw_email = _build_email_with_attachment(_make_pdf(500))

    mock_imap = MagicMock()
    mock_imap.search.return_value = (None, [b"1"])
    mock_imap.fetch.return_value = (None, [(None, raw_email)])

    with (
        patch("haandvaerker.email_poller.imaplib.IMAP4_SSL", return_value=mock_imap),
        patch("haandvaerker.email_poller.ATTACHMENTS_DIR", tmp_path),
    ):
        count = poll_inbox(company_id, session, cfg)

    assert count == 1
    msgs = session.exec(select(InboxMessage).where(InboxMessage.company_id == company_id)).all()
    assert len(msgs) == 1

    attachments = session.exec(
        select(InboxAttachment).where(InboxAttachment.inbox_message_id == msgs[0].id)
    ).all()
    assert len(attachments) == 1
    att = attachments[0]
    assert att.filename == "quote.pdf"
    assert att.content_type == "application/pdf"
    assert att.size_bytes > 0
    assert att.company_id == company_id
    # Disk file must exist
    disk_file = tmp_path / pathlib.Path(att.storage_path).name
    assert disk_file.exists()


def test_imap_poll_skips_disallowed_attachment(
    session: Session, company_id: str, tmp_path: pathlib.Path
):
    """poll_inbox() skips attachments with disallowed types — message still imported."""
    from haandvaerker.email_poller import poll_inbox

    cfg = _make_email_cfg()

    # Build email with .exe attachment
    msg = stdlib_email.mime.multipart.MIMEMultipart()
    msg["Subject"] = "Attachment test"
    msg["From"] = "sender@example.com"
    msg["Date"] = "Mon, 01 Jan 2026 11:00:00 +0000"
    msg.attach(stdlib_email.mime.text.MIMEText("body text", "plain"))
    part = stdlib_email.mime.base.MIMEBase("application", "octet-stream")
    part.set_payload(b"MZ\x90\x00")
    stdlib_email.encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename="evil.exe")
    msg.attach(part)
    raw_email = msg.as_bytes()

    mock_imap = MagicMock()
    mock_imap.search.return_value = (None, [b"1"])
    mock_imap.fetch.return_value = (None, [(None, raw_email)])

    with (
        patch("haandvaerker.email_poller.imaplib.IMAP4_SSL", return_value=mock_imap),
        patch("haandvaerker.email_poller.ATTACHMENTS_DIR", tmp_path),
    ):
        count = poll_inbox(company_id, session, cfg)

    assert count == 1
    msgs = session.exec(select(InboxMessage).where(InboxMessage.company_id == company_id)).all()
    assert len(msgs) == 1
    attachments = session.exec(
        select(InboxAttachment).where(InboxAttachment.inbox_message_id == msgs[0].id)
    ).all()
    assert len(attachments) == 0  # skipped


# ---------------------------------------------------------------------------
# AC-6  GET list — company-scoped
# ---------------------------------------------------------------------------

def test_list_attachments_company_scoped(
    client: TestClient, session: Session, company_id: str, tmp_path: pathlib.Path
):
    """GET /inbox/{id}/attachments only returns attachments for the requesting company."""
    msg = _post_message(client)
    with patch("haandvaerker.api.inbox.ATTACHMENTS_DIR", tmp_path):
        r = _upload(client, msg["id"], "doc.pdf", _make_pdf())
    assert r.status_code == 201

    r = client.get(f"/inbox/{msg['id']}/attachments")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["filename"] == "doc.pdf"


def test_list_attachments_cross_company_blocked(
    client: TestClient, session: Session, company_id: str, tmp_path: pathlib.Path
):
    """Cross-company GET returns 403 (other company's message)."""
    from haandvaerker.models.company import Company
    # Create a second company and a message belonging to it
    other_company = Company(id=str(uuid.uuid4()), name="Anden Firma")
    session.add(other_company)
    session.commit()

    other_msg = InboxMessage(
        id=str(uuid.uuid4()),
        company_id=other_company.id,
        source=InboxSource.email,
        received_at=datetime.now(timezone.utc).replace(tzinfo=None),
        subject="Other company msg",
    )
    session.add(other_msg)
    session.commit()

    # Client is authenticated as company_id (first company)
    r = client.get(f"/inbox/{other_msg.id}/attachments")
    assert r.status_code == 403


def test_list_attachments_returns_empty_for_own_message_without_attachments(
    client: TestClient, tmp_path: pathlib.Path
):
    """GET list on a message with no attachments → 200 empty list."""
    msg = _post_message(client)
    r = client.get(f"/inbox/{msg['id']}/attachments")
    assert r.status_code == 200
    assert r.json() == []


def test_upload_cross_company_message_returns_403(
    client: TestClient, session: Session, company_id: str, tmp_path: pathlib.Path
):
    """POST attachment to another company's message → 403."""
    from haandvaerker.models.company import Company
    other_company = Company(id=str(uuid.uuid4()), name="Tredje Firma")
    session.add(other_company)
    session.commit()

    other_msg = InboxMessage(
        id=str(uuid.uuid4()),
        company_id=other_company.id,
        source=InboxSource.email,
        received_at=datetime.now(timezone.utc).replace(tzinfo=None),
        subject="Other msg",
    )
    session.add(other_msg)
    session.commit()

    with patch("haandvaerker.api.inbox.ATTACHMENTS_DIR", tmp_path):
        r = _upload(client, other_msg.id, "x.pdf", _make_pdf())
    assert r.status_code == 403
