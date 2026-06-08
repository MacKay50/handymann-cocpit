"""Wizard service: confirmation email template and send wrapper."""
from __future__ import annotations

import logging
from typing import Optional

from .smtp_sender import SmtpNotConfiguredError, SmtpSendError, is_smtp_configured, send_email

logger = logging.getLogger(__name__)


def build_confirmation_email(
    customer_name: str, project_title: str, company_name: str
) -> tuple[str, str]:
    """Return (subject, body) as plain-text strings."""
    subject = f"Tak for din henvendelse – {company_name}"
    body = (
        f"Kære {customer_name},\n\n"
        f"Tak for din henvendelse til {company_name}.\n\n"
        f'Vi har oprettet dig som kunde og registreret dit projekt "{project_title}".\n'
        "Vi vender tilbage med et tilbud hurtigst muligt.\n\n"
        "Med venlig hilsen\n"
        f"{company_name}"
    )
    return subject, body


def send_confirmation_email(
    to: str,
    customer_name: str,
    project_title: str,
    company_name: str,
    subject_override: Optional[str] = None,
    body_override: Optional[str] = None,
) -> dict[str, object]:
    """Send confirmation email.

    Returns {"sent": bool, "error": str | None}.
    Never raises — catches SmtpNotConfiguredError and SmtpSendError.
    Logs a WARNING on failure.
    """
    if not is_smtp_configured():
        logger.warning(
            "Confirmation email not sent to %s: SMTP ikke konfigureret", to
        )
        return {"sent": False, "error": "SMTP ikke konfigureret"}

    subject, body = build_confirmation_email(customer_name, project_title, company_name)
    if subject_override:
        subject = subject_override
    if body_override:
        body = body_override
    try:
        send_email(to, subject, body)
    except SmtpNotConfiguredError:
        logger.warning("Confirmation email not sent to %s: SMTP ikke konfigureret", to)
        return {"sent": False, "error": "SMTP ikke konfigureret"}
    except SmtpSendError as exc:
        logger.warning("Confirmation email send failed for %s: %s", to, exc)
        return {"sent": False, "error": str(exc)}
    return {"sent": True, "error": None}
