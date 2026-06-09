"""Unit tests for email_poller.poll_inbox.

Tests cover the actual poll_inbox(company_id, session, cfg) signature.
"""
from __future__ import annotations

import imaplib
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from haandvaerker.email_poller import EmailConfigError, poll_inbox
from haandvaerker.services.config_resolver import EmailConfig


# ── helpers ───────────────────────────────────────────────────────────────────

def _cfg(**overrides) -> EmailConfig:
    base = dict(
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="user@example.com",
        imap_password="secret",  # noqa: S106
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user@example.com",
        smtp_password="secret",  # noqa: S106
        smtp_from="noreply@example.com",
        smtp_use_tls=True,
    )
    base.update(overrides)
    return EmailConfig(**base)


@pytest.fixture()
def mem_session() -> Session:
    """In-memory SQLite session with all tables created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_imap_mock(search_uids: list[bytes] | None = None) -> MagicMock:
    """Return a configured IMAP4_SSL mock that reports an empty inbox."""
    mock_imap = MagicMock()
    uid_bytes = b" ".join(search_uids) if search_uids else b""
    mock_imap.search.return_value = (None, [uid_bytes])
    mock_imap.login.return_value = ("OK", [b"Logged in"])
    mock_imap.select.return_value = ("OK", [b"1"])
    mock_imap.close.return_value = ("OK", [])
    mock_imap.logout.return_value = ("BYE", [])
    return mock_imap


# ── AC-1: raises EmailConfigError when imap_host is missing ──────────────────

def test_poll_inbox_raises_on_missing_imap_host(mem_session: Session) -> None:
    """poll_inbox raises EmailConfigError when cfg.imap_host is empty."""
    cfg = _cfg(imap_host="")
    with pytest.raises(EmailConfigError):
        poll_inbox("company-1", mem_session, cfg)


def test_poll_inbox_raises_on_missing_imap_user(mem_session: Session) -> None:
    """poll_inbox raises EmailConfigError when cfg.imap_user is empty."""
    cfg = _cfg(imap_user="")
    with pytest.raises(EmailConfigError):
        poll_inbox("company-1", mem_session, cfg)


def test_poll_inbox_raises_on_missing_imap_password(mem_session: Session) -> None:
    """poll_inbox raises EmailConfigError when cfg.imap_password is empty."""
    cfg = _cfg(imap_password="")
    with pytest.raises(EmailConfigError):
        poll_inbox("company-1", mem_session, cfg)


# ── AC-2: calls IMAP with credentials from cfg ───────────────────────────────

def test_poll_inbox_calls_imap_with_cfg_credentials(mem_session: Session) -> None:
    """poll_inbox opens IMAP4_SSL using host/port from cfg and logs in with user/password."""
    cfg = _cfg()
    mock_imap = _make_imap_mock()

    with patch("haandvaerker.email_poller.imaplib.IMAP4_SSL", return_value=mock_imap) as mock_cls:
        result = poll_inbox("company-1", mem_session, cfg)

    mock_cls.assert_called_once_with("imap.example.com", 993)
    mock_imap.login.assert_called_once_with("user@example.com", "secret")  # noqa: S106
    assert result == 0  # empty inbox → 0 imported


def test_poll_inbox_returns_zero_on_empty_inbox(mem_session: Session) -> None:
    """poll_inbox returns 0 when IMAP has no UNSEEN messages."""
    cfg = _cfg()
    mock_imap = _make_imap_mock(search_uids=[])

    with patch("haandvaerker.email_poller.imaplib.IMAP4_SSL", return_value=mock_imap):
        result = poll_inbox("company-1", mem_session, cfg)

    assert result == 0


# ── AC-3: IMAP4.error from login propagates ──────────────────────────────────

def test_poll_inbox_propagates_imap4_error(mem_session: Session) -> None:
    """imaplib.IMAP4.error raised during login propagates out of poll_inbox."""
    cfg = _cfg()
    mock_imap = _make_imap_mock()
    mock_imap.login.side_effect = imaplib.IMAP4.error("Authentication failed")

    with patch("haandvaerker.email_poller.imaplib.IMAP4_SSL", return_value=mock_imap):
        with pytest.raises(imaplib.IMAP4.error):
            poll_inbox("company-1", mem_session, cfg)


# ── AC-4: ConnectionRefusedError propagates ──────────────────────────────────

def test_poll_inbox_propagates_connection_refused(mem_session: Session) -> None:
    """ConnectionRefusedError from IMAP4_SSL constructor propagates out of poll_inbox."""
    cfg = _cfg()

    with patch(
        "haandvaerker.email_poller.imaplib.IMAP4_SSL",
        side_effect=ConnectionRefusedError("Connection refused"),
    ):
        with pytest.raises(ConnectionRefusedError):
            poll_inbox("company-1", mem_session, cfg)
