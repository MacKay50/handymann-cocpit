"""Thin SMTP wrapper. Only used for sending invoice reminders.

Raises SmtpNotConfiguredError if SMTP credentials are missing.
Raises SmtpSendError on connection or authentication failure.
All errors include enough context to log and surface to the user.
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USE_TLS, SMTP_USER


class SmtpNotConfiguredError(Exception):
    pass


class SmtpSendError(Exception):
    pass


def is_smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Raises SmtpNotConfiguredError or SmtpSendError."""
    if not is_smtp_configured():
        raise SmtpNotConfiguredError(
            "SMTP ikke konfigureret — udfyld SMTP_HOST, SMTP_USER og SMTP_PASSWORD i .env"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM or SMTP_USER
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as srv:
                srv.ehlo()
                srv.starttls()
                srv.login(SMTP_USER, SMTP_PASSWORD)
                srv.sendmail(msg["From"], [to], msg.as_string())
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as srv:
                srv.login(SMTP_USER, SMTP_PASSWORD)
                srv.sendmail(msg["From"], [to], msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        raise SmtpSendError(f"SMTP autentifikation fejlede: {e}") from e
    except (smtplib.SMTPException, OSError) as e:
        raise SmtpSendError(f"SMTP send fejlede: {e}") from e
