"""Tests for smtp_sender — exercises the parameter-injection signature."""
from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from haandvaerker.services.smtp_sender import SmtpNotConfiguredError, SmtpSendError, send_email
from haandvaerker.services.config_resolver import EmailConfig


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


def test_send_email_raises_not_configured_when_no_smtp_host() -> None:
    """send_email raises SmtpNotConfiguredError when smtp_host is empty."""
    cfg = _cfg(smtp_host="", smtp_user="", smtp_password="")
    with pytest.raises(SmtpNotConfiguredError):
        send_email(to="test@example.com", subject="Test", body="Hello", cfg=cfg)


def test_send_email_tls_success() -> None:
    """send_email calls SMTP.starttls path on success (smtp_use_tls=True)."""
    cfg = _cfg(smtp_use_tls=True)
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = lambda s: s
    mock_smtp.__exit__ = MagicMock(return_value=False)

    with patch("smtplib.SMTP", return_value=mock_smtp):
        send_email(to="to@example.com", subject="Subject", body="Body", cfg=cfg)

    mock_smtp.ehlo.assert_called_once()
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once()
    mock_smtp.sendmail.assert_called_once()


def test_send_email_ssl_success() -> None:
    """send_email calls SMTP_SSL path when smtp_use_tls=False."""
    cfg = _cfg(smtp_use_tls=False)
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = lambda s: s
    mock_smtp.__exit__ = MagicMock(return_value=False)

    with patch("smtplib.SMTP_SSL", return_value=mock_smtp):
        send_email(to="to@example.com", subject="Subject", body="Body", cfg=cfg)

    mock_smtp.login.assert_called_once()
    mock_smtp.sendmail.assert_called_once()


def test_send_email_auth_failure_raises_smtp_send_error() -> None:
    """SMTPAuthenticationError is wrapped in SmtpSendError."""
    cfg = _cfg()
    mock_smtp = MagicMock()
    mock_smtp.__enter__ = lambda s: s
    mock_smtp.__exit__ = MagicMock(return_value=False)
    mock_smtp.starttls = MagicMock()
    mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")

    with patch("smtplib.SMTP", return_value=mock_smtp), pytest.raises(SmtpSendError):
        send_email(to="to@example.com", subject="Subj", body="Body", cfg=cfg)


def test_send_email_os_error_raises_smtp_send_error() -> None:
    """OSError (connection refused) is wrapped in SmtpSendError."""
    cfg = _cfg()
    with patch("smtplib.SMTP", side_effect=OSError("connection refused")), \
         pytest.raises(SmtpSendError):
        send_email(to="to@example.com", subject="Subj", body="Body", cfg=cfg)
