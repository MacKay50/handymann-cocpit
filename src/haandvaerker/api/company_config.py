"""Company email + AI config endpoints.

Password fields are write-only: accepted on PUT, never returned on GET.
GET responses carry imap_password_set / smtp_password_set booleans only.
"""
from __future__ import annotations

import asyncio
import imaplib
import logging
import smtplib
import socket
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..dependencies import CompanyContextDep
from ..models.company_config import (
    CompanyAiConfig,
    CompanyAiConfigRead,
    CompanyAiConfigUpdate,
    CompanyEmailConfig,
    CompanyEmailConfigRead,
    CompanyEmailConfigUpdate,
    CompanyPromptConfig,
    CompanyPromptConfigRead,
    CompanyPromptConfigUpdate,
)
from ..prompts import DRAFT_SYSTEM, DRAFT_USER
from ..services.config_resolver import is_valid_external_host

logger = logging.getLogger(__name__)

router = APIRouter(tags=["company-config"])

_TEST_TIMEOUT = 8  # seconds — hard limit for IMAP+SMTP test


# ── helpers ────────────────────────────────────────────────────────────────────

def _to_email_read(row: CompanyEmailConfig) -> CompanyEmailConfigRead:
    return CompanyEmailConfigRead(
        company_id=row.company_id,
        imap_host=row.imap_host,
        imap_port=row.imap_port,
        imap_user=row.imap_user,
        imap_password_set=bool(row.imap_password),
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_user=row.smtp_user,
        smtp_password_set=bool(row.smtp_password),
        smtp_from=row.smtp_from,
        smtp_use_tls=row.smtp_use_tls,
        updated_at=row.updated_at,
    )


def _to_ai_read(row: CompanyAiConfig) -> CompanyAiConfigRead:
    return CompanyAiConfigRead(
        company_id=row.company_id,
        endpoint=row.endpoint,
        model=row.model,
        fallback_model=row.fallback_model,
        updated_at=row.updated_at,
    )


class AiConfigResponse(BaseModel):
    company_id: str
    endpoint: Optional[str]
    model: Optional[str]
    fallback_model: Optional[str]
    ai_enabled: bool
    updated_at: Optional[datetime] = None


class EmailTestResponse(BaseModel):
    success: bool
    error: Optional[str] = None


# ── email config endpoints ─────────────────────────────────────────────────────

@router.get("/companies/{company_id}/email-config", response_model=CompanyEmailConfigRead)
def get_email_config(company_id: str, ctx: CompanyContextDep) -> CompanyEmailConfigRead:
    """Return email config for the session company. Passwords are never returned."""
    if company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    row = ctx.session.get(CompanyEmailConfig, ctx.company_id)
    if row is None:
        # Return empty config for companies with no row yet
        row = CompanyEmailConfig(
            company_id=ctx.company_id,
            updated_at=datetime.utcnow(),
        )
    return _to_email_read(row)


@router.put("/companies/{company_id}/email-config", response_model=CompanyEmailConfigRead)
def put_email_config(
    company_id: str,
    body: CompanyEmailConfigUpdate,
    ctx: CompanyContextDep,
) -> CompanyEmailConfigRead:
    """Upsert email config. Passwords are write-only: omitting a password preserves the stored one."""
    if company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    session = ctx.session
    row = session.get(CompanyEmailConfig, ctx.company_id)
    if row is None:
        row = CompanyEmailConfig(company_id=ctx.company_id)

    if body.imap_host is not None:
        row.imap_host = body.imap_host
    if body.imap_port is not None:
        row.imap_port = body.imap_port
    if body.imap_user is not None:
        row.imap_user = body.imap_user
    if body.imap_password is not None:
        row.imap_password = body.imap_password
    if body.smtp_host is not None:
        row.smtp_host = body.smtp_host
    if body.smtp_port is not None:
        row.smtp_port = body.smtp_port
    if body.smtp_user is not None:
        row.smtp_user = body.smtp_user
    if body.smtp_password is not None:
        row.smtp_password = body.smtp_password
    if body.smtp_from is not None:
        row.smtp_from = body.smtp_from
    if body.smtp_use_tls is not None:
        row.smtp_use_tls = body.smtp_use_tls

    row.updated_at = datetime.utcnow()

    session.add(row)
    session.commit()
    session.refresh(row)
    return _to_email_read(row)


def _test_imap(host: str, port: int, user: str, password: str) -> Optional[str]:
    """Return None on success, error string on failure."""
    try:
        imap = imaplib.IMAP4_SSL(host, port, timeout=_TEST_TIMEOUT)
        try:
            imap.login(user, password)
        finally:
            try:
                imap.logout()
            except Exception as _exc:  # swallow logout failure; must not mask login result
                logger.debug("IMAP logout cleanup failed (ignored): %s", _exc)
        return None
    except imaplib.IMAP4.error as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"IMAP fejl: {exc}"
    except socket.timeout as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"IMAP timeout: {exc}"
    except ConnectionRefusedError as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"IMAP forbindelse afvist: {exc}"
    except OSError as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"IMAP OS-fejl: {exc}"


def _test_smtp(host: str, port: int, user: str, password: str, use_tls: bool) -> Optional[str]:
    """Return None on success, error string on failure."""
    try:
        if use_tls:
            with smtplib.SMTP(host, port, timeout=6) as srv:
                srv.ehlo()
                srv.starttls()
                srv.login(user, password)
        else:
            with smtplib.SMTP_SSL(host, port, timeout=6) as srv:
                srv.login(user, password)
        return None
    except smtplib.SMTPConnectError as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"SMTP forbindelsesfejl: {exc}"
    except smtplib.SMTPAuthenticationError as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"SMTP godkendelsesfejl: {exc}"
    except socket.timeout as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"SMTP timeout: {exc}"
    except ConnectionRefusedError as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"SMTP forbindelse afvist: {exc}"
    except OSError as exc:
        logger.warning("Email test failed for %s:%s — %s", host, port, exc)
        return f"SMTP OS-fejl: {exc}"


def _run_connection_test(
    imap_host: str,
    imap_port: int,
    imap_user: str,
    imap_password: str,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    smtp_use_tls: bool,
) -> EmailTestResponse:
    imap_err = _test_imap(imap_host, imap_port, imap_user, imap_password)
    if imap_err:
        return EmailTestResponse(success=False, error=imap_err)
    smtp_err = _test_smtp(smtp_host, smtp_port, smtp_user, smtp_password, smtp_use_tls)
    if smtp_err:
        return EmailTestResponse(success=False, error=smtp_err)
    return EmailTestResponse(success=True)


@router.post("/companies/{company_id}/email-config/test", response_model=EmailTestResponse)
async def test_email_config(company_id: str, ctx: CompanyContextDep) -> EmailTestResponse:
    """Test IMAP + SMTP connectivity.

    SSRF guard: loopback/RFC1918/link-local hosts → 422 before any socket.
    Runs blocking I/O in a threadpool with an 8-second hard timeout.
    """
    if company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    row = ctx.session.get(CompanyEmailConfig, ctx.company_id)
    if row is None or not row.imap_host or not row.smtp_host:
        raise HTTPException(
            status_code=422,
            detail="Email-konfiguration mangler — udfyld imap_host og smtp_host først.",
        )

    # SSRF guard — applied before any socket is opened
    for host in (row.imap_host, row.smtp_host):
        if not is_valid_external_host(host):
            raise HTTPException(
                status_code=422,
                detail=f"Ugyldig host '{host}': loopback/intern IP er ikke tilladt.",
            )

    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    executor,
                    _run_connection_test,
                    row.imap_host,
                    row.imap_port,
                    row.imap_user or "",
                    row.imap_password or "",
                    row.smtp_host,
                    row.smtp_port,
                    row.smtp_user or "",
                    row.smtp_password or "",
                    row.smtp_use_tls,
                ),
                timeout=_TEST_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Email test timed out after %ss for company %s",
                _TEST_TIMEOUT,
                ctx.company_id,
            )
            result = EmailTestResponse(
                success=False,
                error=f"Forbindelsestest timeout efter {_TEST_TIMEOUT} sekunder",
            )

    return result


# ── AI config endpoints ────────────────────────────────────────────────────────

@router.get("/companies/{company_id}/ai-config", response_model=AiConfigResponse)
def get_ai_config(company_id: str, ctx: CompanyContextDep) -> AiConfigResponse:
    """Return AI config for the session company.

    Returns ai_enabled=False if no row exists (RISK-07: no global fallback).
    """
    if company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    row = ctx.session.get(CompanyAiConfig, ctx.company_id)
    if row is None:
        return AiConfigResponse(
            company_id=ctx.company_id,
            endpoint=None,
            model=None,
            fallback_model=None,
            ai_enabled=False,
        )
    return AiConfigResponse(
        company_id=row.company_id,
        endpoint=row.endpoint,
        model=row.model,
        fallback_model=row.fallback_model,
        ai_enabled=bool(row.endpoint),
        updated_at=row.updated_at,
    )


@router.put("/companies/{company_id}/ai-config", response_model=AiConfigResponse)
def put_ai_config(
    company_id: str,
    body: CompanyAiConfigUpdate,
    ctx: CompanyContextDep,
) -> AiConfigResponse:
    """Upsert AI config for the session company."""
    if company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    session = ctx.session
    row = session.get(CompanyAiConfig, ctx.company_id)
    if row is None:
        row = CompanyAiConfig(company_id=ctx.company_id)

    if body.endpoint is not None:
        row.endpoint = body.endpoint
    if body.model is not None:
        row.model = body.model
    if body.fallback_model is not None:
        row.fallback_model = body.fallback_model

    row.updated_at = datetime.utcnow()

    session.add(row)
    session.commit()
    session.refresh(row)
    return AiConfigResponse(
        company_id=row.company_id,
        endpoint=row.endpoint,
        model=row.model,
        fallback_model=row.fallback_model,
        ai_enabled=bool(row.endpoint),
        updated_at=row.updated_at,
    )


# ── Prompt config endpoints ────────────────────────────────────────────────────

@router.get("/companies/{company_id}/prompts", response_model=CompanyPromptConfigRead)
def get_prompt_config(company_id: str, ctx: CompanyContextDep) -> CompanyPromptConfigRead:
    """Return prompt config for the session company.

    Returns prompts.py defaults when no DB row exists (updated_at=None).
    """
    if company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    row = ctx.session.get(CompanyPromptConfig, ctx.company_id)
    if row is None:
        return CompanyPromptConfigRead(
            company_id=ctx.company_id,
            draft_system=DRAFT_SYSTEM,
            draft_user=DRAFT_USER,
            updated_at=None,
        )
    return CompanyPromptConfigRead(
        company_id=row.company_id,
        draft_system=row.draft_system if row.draft_system is not None else DRAFT_SYSTEM,
        draft_user=row.draft_user if row.draft_user is not None else DRAFT_USER,
        updated_at=row.updated_at,
    )


@router.put("/companies/{company_id}/prompts", response_model=CompanyPromptConfigRead)
def put_prompt_config(
    company_id: str,
    body: CompanyPromptConfigUpdate,
    ctx: CompanyContextDep,
) -> CompanyPromptConfigRead:
    """Upsert prompt config. Validates that draft_user contains {context} placeholder."""
    if company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if body.draft_user is not None and "{context}" not in body.draft_user:
        raise HTTPException(
            status_code=422,
            detail="draft_user skal indeholde {context} placeholder",
        )

    session = ctx.session
    row = session.get(CompanyPromptConfig, ctx.company_id)
    if row is None:
        row = CompanyPromptConfig(company_id=ctx.company_id)

    if body.draft_system is not None:
        row.draft_system = body.draft_system
    if body.draft_user is not None:
        row.draft_user = body.draft_user

    row.updated_at = datetime.utcnow()

    session.add(row)
    session.commit()
    session.refresh(row)
    return CompanyPromptConfigRead(
        company_id=row.company_id,
        draft_system=row.draft_system if row.draft_system is not None else DRAFT_SYSTEM,
        draft_user=row.draft_user if row.draft_user is not None else DRAFT_USER,
        updated_at=row.updated_at,
    )
