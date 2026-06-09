from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── POST /quote-preparations/ ─────────────────────────────────────────────────


def test_create_preparation_minimal(client: TestClient, company_id: str) -> None:
    """POST with customer_name only → 201, inbox_message_id null, status draft."""
    r = client.post("/quote-preparations/", json={"customer_name": "Test"})
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["status"] == "draft"
    assert data["inbox_message_id"] is None
    assert data["company_id"] == company_id
    assert data["customer_name"] == "Test"


def test_create_preparation_no_name(client: TestClient) -> None:
    """POST with missing customer_name → 422 (field required)."""
    r = client.post("/quote-preparations/", json={})
    assert r.status_code == 422, r.json()
    detail = r.json()["detail"]
    assert any("customer_name" in str(item) for item in detail)


def test_create_preparation_empty_name(client: TestClient) -> None:
    """POST with empty string customer_name → 422 (min_length=1)."""
    r = client.post("/quote-preparations/", json={"customer_name": ""})
    assert r.status_code == 422, r.json()
    detail = r.json()["detail"]
    assert any("customer_name" in str(item) for item in detail)


def test_create_preparation_duplicate_id(client: TestClient) -> None:
    """Posting the same id twice → second call returns 409."""
    fixed_id = str(uuid.uuid4())
    r1 = client.post("/quote-preparations/", json={"id": fixed_id, "customer_name": "Alice"})
    assert r1.status_code == 201, r1.json()
    r2 = client.post("/quote-preparations/", json={"id": fixed_id, "customer_name": "Alice"})
    assert r2.status_code == 409, r2.json()


def test_create_preparation_custom_id_roundtrip(client: TestClient) -> None:
    """If id is provided, the returned record uses that id."""
    fixed_id = str(uuid.uuid4())
    r = client.post("/quote-preparations/", json={"id": fixed_id, "customer_name": "Bob"})
    assert r.status_code == 201
    assert r.json()["id"] == fixed_id


def test_create_preparation_all_fields(client: TestClient) -> None:
    """All optional fields are accepted and returned."""
    payload: dict[str, Any] = {
        "customer_name": "Søren",
        "customer_email": "soeren@example.com",
        "customer_phone": "12345678",
        "address": "Nørregade 1, 1165 København K",
        "task_type": "malerarbejde",
        "short_summary": "Maling af stue",
        "detailed_description": "Vægge og lofter",
        "internal_notes": "Ring først",
    }
    r = client.post("/quote-preparations/", json=payload)
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["customer_email"] == "soeren@example.com"
    assert data["task_type"] == "malerarbejde"


# ── backward-compat tests for quote_preparations ──────────────────────────────


def _post_inbox(client: TestClient, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": "email",
        "received_at": "2026-05-20T09:00:00",
        "sender_name": "Lars Jensen",
        "sender_email": "lars@example.com",
        "subject": "Forespørgsel om malerarbejde",
        "body": "Hej, vi ønsker maling af Strandvej 42, 2900 Hellerup.",
        **extra,
    }
    r = client.post("/inbox/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()  # type: ignore[return-value]


def test_from_inbox_backward_compat(client: TestClient) -> None:
    """from-inbox still returns a QuotePreparationRead with inbox_message_id populated."""
    msg = _post_inbox(client)
    r = client.post(f"/quote-preparations/from-inbox/{msg['id']}")
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["inbox_message_id"] == msg["id"]
    assert data["inbox_message_id"] is not None
    assert data["status"] == "draft"


def test_patch_works_on_direct_creation(client: TestClient) -> None:
    """Create via POST /quote-preparations/, then PATCH it — same handler, works."""
    create_r = client.post("/quote-preparations/", json={"customer_name": "Initial"})
    assert create_r.status_code == 201
    qp_id = create_r.json()["id"]

    patch_r = client.patch(
        f"/quote-preparations/{qp_id}",
        json={"customer_name": "Updated", "address": "Ny Vej 2"},
    )
    assert patch_r.status_code == 200, patch_r.json()
    data = patch_r.json()
    assert data["customer_name"] == "Updated"
    assert data["address"] == "Ny Vej 2"


# ── wizard_service unit tests ─────────────────────────────────────────────────


def test_build_confirmation_email() -> None:
    """build_confirmation_email returns a (subject, body) tuple with expected strings."""
    from haandvaerker.services.wizard_service import build_confirmation_email

    subject, body = build_confirmation_email(
        customer_name="Mette",
        project_title="Malerarbejde",
        company_name="Firma A/S",
    )
    assert isinstance(subject, str)
    assert isinstance(body, str)
    assert "Firma A/S" in subject
    assert "Mette" in body
    assert "Firma A/S" in body
    assert "Malerarbejde" in body


def test_send_confirmation_email_no_smtp() -> None:
    """When resolve_email_config returns None, returns {"sent": False, "error": ...}."""
    from haandvaerker.services.wizard_service import send_confirmation_email

    with patch(
        "haandvaerker.services.wizard_service.resolve_email_config", return_value=None
    ):
        from unittest.mock import MagicMock
        mock_session = MagicMock()
        result = send_confirmation_email(
            to="test@example.com",
            customer_name="Mette",
            project_title="Malerarbejde",
            company_name="Firma A/S",
            session=mock_session,
            company_id="test-company",
        )
    assert result["sent"] is False
    assert result["error"] is not None


def test_send_confirmation_email_smtp_send_error() -> None:
    """When send_email raises SmtpSendError, returns {"sent": False, "error": ...}."""
    from unittest.mock import MagicMock
    from haandvaerker.services.smtp_sender import SmtpSendError
    from haandvaerker.services.wizard_service import send_confirmation_email
    from haandvaerker.services.config_resolver import EmailConfig

    fake_cfg = EmailConfig(
        imap_host="h", imap_port=993, imap_user="u", imap_password="p",
        smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
        smtp_from="f", smtp_use_tls=True,
    )
    mock_session = MagicMock()
    with patch(
        "haandvaerker.services.wizard_service.resolve_email_config", return_value=fake_cfg
    ), patch(
        "haandvaerker.services.wizard_service.send_email",
        side_effect=SmtpSendError("connection refused"),
    ):
        result = send_confirmation_email(
            to="test@example.com",
            customer_name="Mette",
            project_title="Malerarbejde",
            company_name="Firma A/S",
            session=mock_session,
            company_id="test-company",
        )
    assert result["sent"] is False
    assert "connection refused" in (result["error"] or "")


def test_send_confirmation_email_success() -> None:
    """When send_email succeeds, returns {"sent": True, "error": None}."""
    from unittest.mock import MagicMock
    from haandvaerker.services.wizard_service import send_confirmation_email
    from haandvaerker.services.config_resolver import EmailConfig

    fake_cfg = EmailConfig(
        imap_host="h", imap_port=993, imap_user="u", imap_password="p",
        smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="p",
        smtp_from="f", smtp_use_tls=True,
    )
    mock_session = MagicMock()
    with patch(
        "haandvaerker.services.wizard_service.resolve_email_config", return_value=fake_cfg
    ), patch(
        "haandvaerker.services.wizard_service.send_email", return_value=None
    ):
        result = send_confirmation_email(
            to="test@example.com",
            customer_name="Mette",
            project_title="Malerarbejde",
            company_name="Firma A/S",
            session=mock_session,
            company_id="test-company",
        )
    assert result["sent"] is True
    assert result["error"] is None


# ── POST /wizard/cvr-lookup ───────────────────────────────────────────────────


def _cvr_response_bytes(name: str, address: str, phone: str) -> bytes:
    return json.dumps(
        {"name": name, "address": address, "phone": phone, "city": "København", "zipcode": "1165"}
    ).encode()


def test_cvr_lookup_success(client: TestClient) -> None:
    """Stubbed cvrapi.dk success → 200, looked_up=True, fields populated."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = _cvr_response_bytes(
        "Mester Murers A/S", "Nørregade 1", "33445566"
    )
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("haandvaerker.api.wizard.request.urlopen", return_value=mock_resp):
        r = client.post("/wizard/cvr-lookup", json={"cvr_number": "12345678"})

    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["looked_up"] is True
    assert data["name"] == "Mester Murers A/S"
    assert data["address"] == "Nørregade 1"
    assert data["phone"] == "33445566"


def test_cvr_lookup_network_failure(client: TestClient) -> None:
    """URLError → 200, looked_up=False, empty strings — never 4xx/5xx."""
    import urllib.error

    with patch(
        "haandvaerker.api.wizard.request.urlopen",
        side_effect=urllib.error.URLError("network unreachable"),
    ):
        r = client.post("/wizard/cvr-lookup", json={"cvr_number": "00000000"})

    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["looked_up"] is False
    assert data["name"] == ""
    assert data["address"] == ""
    assert data["phone"] == ""


def test_cvr_lookup_json_error(client: TestClient) -> None:
    """Malformed JSON from cvrapi → 200, looked_up=False."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"not-json"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("haandvaerker.api.wizard.request.urlopen", return_value=mock_resp):
        r = client.post("/wizard/cvr-lookup", json={"cvr_number": "12345678"})

    assert r.status_code == 200, r.json()
    assert r.json()["looked_up"] is False


# ── POST /wizard/suggestions ──────────────────────────────────────────────────


def _make_historical_offer(**kwargs: Any):  # type: ignore[misc]
    """Return a minimal HistoricalOffer-like object for mocking keyword_search."""
    from unittest.mock import MagicMock
    offer = MagicMock()
    offer.treatment = kwargs.get("treatment", "")
    offer.materials = kwargs.get("materials", "")
    offer.estimated_hours = kwargs.get("estimated_hours", None)
    return offer


def test_suggestions_keyword_only(client: TestClient) -> None:
    """POST /wizard/suggestions → keyword result drives suggested_lines; ai_used=False."""
    offer = _make_historical_offer(treatment="Maling af vægge", estimated_hours=8.0)

    with patch("haandvaerker.api.wizard.keyword_search", return_value=[offer]), \
         patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=False):
        r = client.post("/wizard/suggestions", json={"work_type": "maling"})

    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["ai_used"] is False
    assert data["matched_offers_count"] == 1
    assert len(data["suggested_lines"]) >= 1
    assert any(line["source"] == "history" for line in data["suggested_lines"])
    assert any("maling" in line["description"].lower() for line in data["suggested_lines"])


def test_suggestions_no_offers(client: TestClient) -> None:
    """POST /wizard/suggestions with no keyword matches → empty suggested_lines."""
    with patch("haandvaerker.api.wizard.keyword_search", return_value=[]), \
         patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=False):
        r = client.post("/wizard/suggestions", json={"work_type": "xyz-ingen-match"})

    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["suggested_lines"] == []
    assert data["ai_used"] is False
    assert data["matched_offers_count"] == 0


def test_suggestions_ai_disabled(client: TestClient) -> None:
    """When is_enabled()=False, ai_used is False even when description is provided."""
    offer = _make_historical_offer(treatment="Spartling af vægge")

    with patch("haandvaerker.api.wizard.keyword_search", return_value=[offer]), \
         patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=False):
        r = client.post(
            "/wizard/suggestions",
            json={"work_type": "spartling", "description": "Stuen skal spartles"},
        )

    assert r.status_code == 200, r.json()
    assert r.json()["ai_used"] is False


def test_suggestions_ai_enabled_valid_json(client: TestClient) -> None:
    """When is_enabled()=True and chat_completion returns valid JSON, ai_used=True."""
    ai_lines = json.dumps([
        {"description": "AI linje 1", "unit": "time", "unit_price": 450.0},
        {"description": "AI linje 2", "unit": "m2", "unit_price": 120.0},
    ])

    with patch("haandvaerker.api.wizard.keyword_search", return_value=[]), \
         patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=True), \
         patch("haandvaerker.api.wizard.local_ai.chat_completion", return_value=ai_lines):
        r = client.post(
            "/wizard/suggestions",
            json={"work_type": "maling", "description": "Stuen skal males"},
        )

    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["ai_used"] is True
    ai_descriptions = [line["description"] for line in data["suggested_lines"] if line["source"] == "ai"]
    assert "AI linje 1" in ai_descriptions
    assert "AI linje 2" in ai_descriptions


def test_suggestions_ai_enabled_invalid_json(client: TestClient) -> None:
    """When chat_completion returns invalid JSON, ai_used=False (graceful fallback)."""
    with patch("haandvaerker.api.wizard.keyword_search", return_value=[]), \
         patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=True), \
         patch("haandvaerker.api.wizard.local_ai.chat_completion", return_value="not json"):
        r = client.post(
            "/wizard/suggestions",
            json={"work_type": "maling", "description": "Noget arbejde"},
        )

    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["ai_used"] is False
    assert data["suggested_lines"] == []


def test_suggestions_ai_returns_none(client: TestClient) -> None:
    """When chat_completion returns None, ai_used=False (graceful fallback)."""
    with patch("haandvaerker.api.wizard.keyword_search", return_value=[]), \
         patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=True), \
         patch("haandvaerker.api.wizard.local_ai.chat_completion", return_value=None):
        r = client.post(
            "/wizard/suggestions",
            json={"work_type": "maling", "description": "Noget arbejde"},
        )

    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["ai_used"] is False


def test_suggestions_deduplicates_by_description(client: TestClient) -> None:
    """Duplicate descriptions (case-insensitive) are deduplicated; max 5 lines returned."""
    # Create 6 offers with the same treatment text
    offers = [_make_historical_offer(treatment="Maling af vægge") for _ in range(6)]

    with patch("haandvaerker.api.wizard.keyword_search", return_value=offers), \
         patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=False):
        r = client.post("/wizard/suggestions", json={"work_type": "maling"})

    assert r.status_code == 200, r.json()
    data = r.json()
    # Deduplicated: all same description → 1 line, and max 5 anyway
    assert len(data["suggested_lines"]) <= 5
    descriptions = [line["description"].lower() for line in data["suggested_lines"]]
    assert len(descriptions) == len(set(descriptions)), "Descriptions must be unique"


def test_suggestions_max_5_lines(client: TestClient) -> None:
    """At most 5 suggested_lines are returned."""
    offers = [
        _make_historical_offer(treatment=f"Behandling {i}", materials=f"Materiale {i}")
        for i in range(10)
    ]

    with patch("haandvaerker.api.wizard.keyword_search", return_value=offers), \
         patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=False):
        r = client.post("/wizard/suggestions", json={"work_type": "maling"})

    assert r.status_code == 200, r.json()
    assert len(r.json()["suggested_lines"]) <= 5


def test_suggestions_work_type_too_long_returns_422(client: TestClient) -> None:
    """work_type > 200 chars → 422 (field validation)."""
    r = client.post("/wizard/suggestions", json={"work_type": "x" * 201})
    assert r.status_code == 422, r.json()


def test_suggestions_missing_work_type_returns_422(client: TestClient) -> None:
    """Missing work_type → 422 (required field)."""
    r = client.post("/wizard/suggestions", json={})
    assert r.status_code == 422, r.json()


# ── convert-to-flow backward compat ──────────────────────────────────────────


def test_convert_to_flow_no_body_still_201(client: TestClient) -> None:
    """Call convert-to-flow with no body (old style) → 201 (backward compat)."""
    payload: dict[str, Any] = {
        "source": "email",
        "received_at": "2026-05-20T09:00:00",
        "sender_name": "Karin Olsen",
        "sender_email": "karin@example.com",
        "subject": "Tilbud på rør",
        "body": "Hej, VVS-arbejde ønskes. Adresse: Holmevej 1, 4000 Roskilde.",
    }
    inbox_r = client.post("/inbox/", json=payload)
    assert inbox_r.status_code == 201, inbox_r.json()
    msg = inbox_r.json()
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    r = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow")
    assert r.status_code == 201, r.json()


# ── Phase 4: GET /wizard page ─────────────────────────────────────────────────


def test_wizard_page_returns_200(client: TestClient) -> None:
    """GET /wizard returns 200 with Content-Type: text/html."""
    r = client.get("/wizard")
    assert r.status_code == 200, r.text
    assert "text/html" in r.headers.get("content-type", "")


def test_wizard_page_has_step_indicator(client: TestClient) -> None:
    """Response body contains data-wizard-step attribute or the string 'Trin 1'."""
    r = client.get("/wizard")
    assert r.status_code == 200, r.text
    body = r.text
    assert "data-wizard-step" in body or "Trin 1" in body


def test_wizard_page_has_smtp_status_attr(client: TestClient) -> None:
    """Response body contains the data-smtp-status attribute (AC-5b)."""
    r = client.get("/wizard")
    assert r.status_code == 200, r.text
    assert "data-smtp-status" in r.text


# ── POST /wizard/ai-draft ─────────────────────────────────────────────────────


def test_ai_draft_ai_disabled(client: TestClient) -> None:
    """When Ollama is disabled, ai_used=False and fields are empty strings."""
    with patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=False):
        r = client.post("/wizard/ai-draft", json={"task_type": "malerarbejde"})
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["ai_used"] is False
    assert data["short_summary"] == ""
    assert data["detailed_description"] == ""


def test_ai_draft_ai_enabled_valid_json(client: TestClient) -> None:
    """When AI returns valid JSON, ai_used=True and fields are populated."""
    ai_response = json.dumps({
        "short_summary": "Malerarbejde i enfamiliehus",
        "detailed_description": "Maling af stue og soveværelse inkl. lofter.",
    })
    with patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=True), \
         patch("haandvaerker.api.wizard.local_ai.chat_completion", return_value=ai_response):
        r = client.post("/wizard/ai-draft", json={
            "task_type": "malerarbejde",
            "customer_name": "Lars Hansen",
            "address": "Skovvej 12, 2100 København Ø",
        })
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["ai_used"] is True
    assert "maler" in data["short_summary"].lower() or len(data["short_summary"]) > 0
    assert len(data["detailed_description"]) > 0


def test_ai_draft_ai_invalid_json(client: TestClient) -> None:
    """When AI returns non-JSON, ai_used=False and fields are empty — no crash."""
    with patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=True), \
         patch("haandvaerker.api.wizard.local_ai.chat_completion", return_value="ikke json"):
        r = client.post("/wizard/ai-draft", json={"task_type": "tømrerarbejde"})
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["ai_used"] is False
    assert data["short_summary"] == ""


def test_ai_draft_ai_returns_none(client: TestClient) -> None:
    """When chat_completion returns None (Ollama down), ai_used=False — no crash."""
    with patch("haandvaerker.api.wizard.local_ai.is_enabled", return_value=True), \
         patch("haandvaerker.api.wizard.local_ai.chat_completion", return_value=None):
        r = client.post("/wizard/ai-draft", json={"task_type": "VVS"})
    assert r.status_code == 200, r.json()
    assert r.json()["ai_used"] is False


def test_ai_draft_empty_task_type_returns_422(client: TestClient) -> None:
    """Empty task_type → 422."""
    r = client.post("/wizard/ai-draft", json={"task_type": ""})
    assert r.status_code == 422, r.json()
