"""Centralised per-company config resolution.

DB-first for email/SMTP; DB-only for AI (RISK-07).
"""
from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session

from ..config import (
    EMAIL_IMAP_HOST,
    EMAIL_IMAP_PORT,
    EMAIL_PASSWORD,
    EMAIL_USER,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    imap_host: str
    imap_port: int
    imap_user: str
    imap_password: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_use_tls: bool


@dataclass
class AiConfig:
    endpoint: str
    model: str
    fallback_model: str


def resolve_email_config(session: Session, company_id: str) -> Optional[EmailConfig]:
    """DB-first. Falls back to .env if no DB row — logged once at INFO per company.

    Returns None if neither DB nor .env has usable config.
    Legitimate boot/operator fallback, not runtime masking (see plan §Approach).
    """
    from ..models.company_config import CompanyEmailConfig

    row = session.get(CompanyEmailConfig, company_id)
    if row and row.imap_host and row.smtp_host:
        return EmailConfig(
            imap_host=row.imap_host,
            imap_port=row.imap_port,
            imap_user=row.imap_user or "",
            imap_password=row.imap_password or "",
            smtp_host=row.smtp_host,
            smtp_port=row.smtp_port,
            smtp_user=row.smtp_user or "",
            smtp_password=row.smtp_password or "",
            smtp_from=row.smtp_from or row.smtp_user or "",
            smtp_use_tls=row.smtp_use_tls,
        )

    # .env fallback — legitimate boot/operator fallback; logged at INFO
    if EMAIL_IMAP_HOST and SMTP_HOST:
        logger.info(
            "Company %s: no DB email config — using .env fallback", company_id
        )
        return EmailConfig(
            imap_host=EMAIL_IMAP_HOST,
            imap_port=EMAIL_IMAP_PORT,
            imap_user=EMAIL_USER,
            imap_password=EMAIL_PASSWORD,
            smtp_host=SMTP_HOST,
            smtp_port=SMTP_PORT,
            smtp_user=SMTP_USER,
            smtp_password=SMTP_PASSWORD,
            smtp_from=SMTP_FROM,
            smtp_use_tls=SMTP_USE_TLS,
        )

    return None


def resolve_ai_config(session: Session, company_id: str) -> Optional[AiConfig]:
    """DB-only — no .env fallback for AI (RISK-07).

    Returns None if no DB row or row has no endpoint.
    """
    from ..models.company_config import CompanyAiConfig

    row = session.get(CompanyAiConfig, company_id)
    if row and row.endpoint:
        return AiConfig(
            endpoint=row.endpoint,
            model=row.model or "mistral",
            fallback_model=row.fallback_model or "",
        )
    return None


def is_valid_external_host(host: str) -> bool:
    """SSRF guard — returns False for loopback, RFC1918, link-local, localhost."""
    blocked_names = {"localhost", "localhost.localdomain"}
    if host.lower() in blocked_names:
        return False
    try:
        addr = ipaddress.ip_address(host)
        return not (addr.is_loopback or addr.is_private or addr.is_link_local)
    except ValueError:
        # It is a hostname — allow external hostnames (e.g. smtp.gmail.com)
        return True
