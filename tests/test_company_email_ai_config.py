"""Tests for Phase 2: company email + AI config endpoints and service parameter-injection."""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ── helpers ────────────────────────────────────────────────────────────────────

def _put_email_cfg(client: TestClient, company_id: str, **kwargs) -> dict:
    payload = {
        "imap_host": "imap.example.com",
        "imap_port": 993,
        "imap_user": "user@example.com",
        "imap_password": "secret123",  # noqa: S106
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "user@example.com",
        "smtp_password": "secret456",  # noqa: S106
        "smtp_from": "noreply@example.com",
        "smtp_use_tls": True,
        **kwargs,
    }
    r = client.put(f"/companies/{company_id}/email-config", json=payload)
    assert r.status_code == 200, r.json()
    return r.json()


# ── AC-1: GET never returns password fields ───────────────────────────────────

def test_email_config_never_returns_password(client: TestClient, company_id: str) -> None:
    """GET /companies/{id}/email-config must never include password fields."""
    _put_email_cfg(client, company_id)
    r = client.get(f"/companies/{company_id}/email-config")
    assert r.status_code == 200, r.json()
    data = r.json()
    # password fields must never appear
    assert "imap_password" not in data
    assert "smtp_password" not in data
    # password_set booleans must appear
    assert "imap_password_set" in data
    assert "smtp_password_set" in data
    assert data["imap_password_set"] is True
    assert data["smtp_password_set"] is True


# ── AC-2: PUT + GET round-trip, password_set=true after PUT ───────────────────

def test_email_config_password_write_only(client: TestClient, company_id: str) -> None:
    """PUT with password → password_set=true; PUT with password=None keeps existing."""
    _put_email_cfg(client, company_id)

    r = client.get(f"/companies/{company_id}/email-config")
    assert r.status_code == 200
    data = r.json()
    assert data["imap_password_set"] is True
    assert data["smtp_password_set"] is True
    assert data["imap_host"] == "imap.example.com"

    # PUT again without passwords — existing passwords should be preserved
    r2 = client.put(f"/companies/{company_id}/email-config", json={
        "imap_host": "imap2.example.com",
        "smtp_host": "smtp2.example.com",
    })
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["imap_host"] == "imap2.example.com"
    assert data2["imap_password_set"] is True   # password preserved
    assert data2["smtp_password_set"] is True   # password preserved


# ── AC-3: test-endpoint returns structured error for unreachable host ──────────

def test_email_test_times_out_fast(client: TestClient, company_id: str) -> None:
    """POST .../email-config/test returns {"success": false, "error": ...} within 10s."""
    _put_email_cfg(client, company_id, imap_host="smtp.external-unreachable.invalid", smtp_host="smtp.external-unreachable.invalid")
    start = time.monotonic()
    r = client.post(f"/companies/{company_id}/email-config/test")
    elapsed = time.monotonic() - start
    assert elapsed < 10.0, f"Test took {elapsed:.1f}s, expected < 10s"
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["success"] is False
    assert isinstance(data.get("error"), str)
    assert len(data["error"]) > 0


# ── AC-4: SSRF guard rejects loopback/RFC1918 before any socket ──────────────

def test_email_test_ssrf_guard(client: TestClient, company_id: str) -> None:
    """POST .../email-config/test with host=127.0.0.1 → 422, no socket opened."""
    _put_email_cfg(client, company_id, imap_host="127.0.0.1", smtp_host="127.0.0.1")

    import socket
    original_connect = socket.create_connection
    connect_called = []

    def spy_connect(*args, **kwargs):
        connect_called.append(args)
        return original_connect(*args, **kwargs)

    with patch("socket.create_connection", side_effect=spy_connect):
        r = client.post(f"/companies/{company_id}/email-config/test")

    assert r.status_code == 422, r.json()
    assert connect_called == [], "No socket should have been opened for SSRF host"


def test_email_test_ssrf_guard_private_ip(client: TestClient, company_id: str) -> None:
    """POST .../email-config/test with host=10.0.0.1 → 422 (RFC1918)."""
    _put_email_cfg(client, company_id, imap_host="10.0.0.1", smtp_host="10.0.0.1")
    r = client.post(f"/companies/{company_id}/email-config/test")
    assert r.status_code == 422, r.json()


def test_email_test_ssrf_guard_localhost(client: TestClient, company_id: str) -> None:
    """POST .../email-config/test with host=localhost → 422."""
    _put_email_cfg(client, company_id, imap_host="localhost", smtp_host="localhost")
    r = client.post(f"/companies/{company_id}/email-config/test")
    assert r.status_code == 422, r.json()


# ── AC-5: AI config — disabled for company without row ────────────────────────

def test_ai_disabled_without_row(client: TestClient, company_id: str) -> None:
    """GET /companies/{id}/ai-config with no row → ai_enabled=False."""
    r = client.get(f"/companies/{company_id}/ai-config")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["ai_enabled"] is False


def test_ai_config_put_get_roundtrip(client: TestClient, company_id: str) -> None:
    """PUT then GET /companies/{id}/ai-config round-trips stored values."""
    r = client.put(f"/companies/{company_id}/ai-config", json={
        "endpoint": "http://ai.external.example.com:11434",
        "model": "llama3",
        "fallback_model": "mistral",
    })
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["endpoint"] == "http://ai.external.example.com:11434"
    assert data["model"] == "llama3"
    assert data["ai_enabled"] is True

    r2 = client.get(f"/companies/{company_id}/ai-config")
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["endpoint"] == "http://ai.external.example.com:11434"
    assert data2["ai_enabled"] is True


# ── is_valid_external_host unit tests ─────────────────────────────────────────

def test_ssrf_guard_unit() -> None:
    """is_valid_external_host rejects known bad hosts and allows good ones."""
    from haandvaerker.services.config_resolver import is_valid_external_host

    assert is_valid_external_host("smtp.gmail.com") is True
    assert is_valid_external_host("mail.simply.com") is True
    assert is_valid_external_host("127.0.0.1") is False
    assert is_valid_external_host("localhost") is False
    assert is_valid_external_host("10.0.0.1") is False
    assert is_valid_external_host("192.168.1.100") is False
    assert is_valid_external_host("172.16.0.1") is False


# ── resolve_email_config unit tests ───────────────────────────────────────────

def test_resolve_email_config_db_first(session) -> None:
    """resolve_email_config returns DB row when present."""
    import uuid
    from haandvaerker.models.company import Company
    from haandvaerker.models.company_config import CompanyEmailConfig
    from haandvaerker.services.config_resolver import resolve_email_config

    cid = str(uuid.uuid4())
    session.add(Company(id=cid, name="Test Corp"))
    session.add(CompanyEmailConfig(
        company_id=cid,
        imap_host="imap.db.example.com",
        imap_port=993,
        imap_user="u",
        imap_password="p",
        smtp_host="smtp.db.example.com",
        smtp_port=587,
        smtp_user="u",
        smtp_password="p",
        smtp_from="noreply@db.example.com",
        smtp_use_tls=True,
    ))
    session.commit()

    cfg = resolve_email_config(session, cid)
    assert cfg is not None
    assert cfg.imap_host == "imap.db.example.com"
    assert cfg.smtp_host == "smtp.db.example.com"


def test_resolve_email_config_none_when_missing(session) -> None:
    """resolve_email_config returns None for company with no DB row and no .env."""
    import uuid
    from haandvaerker.models.company import Company
    from haandvaerker.services.config_resolver import resolve_email_config

    cid = str(uuid.uuid4())
    session.add(Company(id=cid, name="No Config Corp"))
    session.commit()

    # Patch .env constants to empty so fallback returns None
    with patch("haandvaerker.services.config_resolver.EMAIL_IMAP_HOST", ""), \
         patch("haandvaerker.services.config_resolver.SMTP_HOST", ""):
        cfg = resolve_email_config(session, cid)

    assert cfg is None


def test_resolve_ai_config_none_when_missing(session) -> None:
    """resolve_ai_config returns None for company without AI row (RISK-07)."""
    import uuid
    from haandvaerker.models.company import Company
    from haandvaerker.services.config_resolver import resolve_ai_config

    cid = str(uuid.uuid4())
    session.add(Company(id=cid, name="No AI Corp"))
    session.commit()

    cfg = resolve_ai_config(session, cid)
    assert cfg is None
