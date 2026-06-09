"""Tests for GET/PUT /companies/{company_id}/prompts endpoints.

Covers:
  - Default response when no DB row exists (returns prompts.py values)
  - Persist on PUT, retrieve on GET
  - 422 when draft_user is missing {context} placeholder
  - GET after PUT returns saved values, not defaults
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from haandvaerker.prompts import DRAFT_SYSTEM, DRAFT_USER


def test_get_prompts_returns_defaults_when_no_row(client: TestClient, company_id: str) -> None:
    """GET with no CompanyPromptConfig row → returns DRAFT_SYSTEM / DRAFT_USER from prompts.py."""
    r = client.get(f"/companies/{company_id}/prompts")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["draft_system"] == DRAFT_SYSTEM
    assert data["draft_user"] == DRAFT_USER
    assert data["updated_at"] is None


def test_put_prompts_persists(client: TestClient, company_id: str) -> None:
    """PUT with valid draft_system + draft_user (containing {context}) → 200, values stored."""
    payload = {
        "draft_system": "Du er en specialiseret assistent.",
        "draft_user": "Her er konteksten: {context}\n\nSvar venligst.",
    }
    r = client.put(f"/companies/{company_id}/prompts", json=payload)
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["draft_system"] == payload["draft_system"]
    assert data["draft_user"] == payload["draft_user"]
    assert data["updated_at"] is not None


def test_put_prompts_rejects_missing_context_placeholder(client: TestClient, company_id: str) -> None:
    """PUT with draft_user that lacks {context} → 422."""
    payload = {
        "draft_user": "Skriv et udkast uden placeholder",
    }
    r = client.put(f"/companies/{company_id}/prompts", json=payload)
    assert r.status_code == 422, r.json()


def test_put_prompts_context_placeholder_required(client: TestClient, company_id: str) -> None:
    """PUT with draft_user = 'Skriv et udkast' (no {context}) → 422 with error mentioning {context}."""
    payload = {
        "draft_user": "Skriv et udkast",
    }
    r = client.put(f"/companies/{company_id}/prompts", json=payload)
    assert r.status_code == 422, r.json()
    # The error detail must mention {context}
    detail = r.json().get("detail", "")
    assert "{context}" in str(detail), f"Expected '{{context}}' in error detail, got: {detail}"


def test_get_prompts_returns_db_values_when_row_exists(client: TestClient, company_id: str) -> None:
    """GET after PUT → returns the stored values, not prompts.py defaults."""
    custom_system = "Custom system prompt."
    custom_user = "Kontekst: {context}\nSvar på dansk."
    client.put(f"/companies/{company_id}/prompts", json={
        "draft_system": custom_system,
        "draft_user": custom_user,
    })

    r = client.get(f"/companies/{company_id}/prompts")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["draft_system"] == custom_system
    assert data["draft_user"] == custom_user
    assert data["updated_at"] is not None


def test_get_prompts_404_if_company_not_found(client: TestClient) -> None:
    """GET with a company_id that doesn't match the session → 403."""
    r = client.get("/companies/nonexistent-company/prompts")
    assert r.status_code == 403, r.json()
