"""Thin SMTP wrapper. Only used for sending invoice reminders.

Raises SmtpNotConfiguredError if SMTP credentials are missing.
Raises SmtpSendError on connection or authentication failure.
All errors include enough context to log and surface to the user.
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config_resolver import EmailConfig


class SmtpNotConfiguredError(Exception):
    pass


class SmtpSendError(Exception):
    pass


def send_email(to: str, subject: str, body: str, cfg: EmailConfig) -> None:
    """Send a plain-text email using the provided config.

    Raises SmtpNotConfiguredError if smtp_host/user/password are absent.
    Raises SmtpSendError on connection or authentication failure.
    """
    if not (cfg.smtp_host and cfg.smtp_user and cfg.smtp_password):
        raise SmtpNotConfiguredError(
            "SMTP ikke konfigureret — udfyld SMTP_HOST, SMTP_USER og SMTP_PASSWORD"
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_from or cfg.smtp_user
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        if cfg.smtp_use_tls:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as srv:
                srv.ehlo()
                srv.starttls()
                srv.login(cfg.smtp_user, cfg.smtp_password)
                srv.sendmail(msg["From"], [to], msg.as_string())
        else:
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15) as srv:
                srv.login(cfg.smtp_user, cfg.smtp_password)
                srv.sendmail(msg["From"], [to], msg.as_string())
    except smtplib.SMTPAuthenticationError as e:
        raise SmtpSendError(f"SMTP autentifikation fejlede: {e}") from e
    except (smtplib.SMTPException, OSError) as e:
        raise SmtpSendError(f"SMTP send fejlede: {e}") from e
