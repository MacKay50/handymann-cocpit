from typing import Optional
from unittest.mock import patch

from fastapi.testclient import TestClient


def _post_inbox(client: TestClient, **extra) -> dict:
    payload = {
        "source": "email",
        "received_at": "2026-05-20T09:00:00",
        "sender_name": "Lars Jensen",
        "sender_email": "lars@example.com",
        "subject": "Forespørgsel om malerarbejde i lejlighed",
        "body": "Hej, vi har brug for maling af vores lejlighed på Strandvej 42, 2900 Hellerup. "
                "Vi mangler maling af vægge og lofter. Kan I give et tilbud?",
        **extra,
    }
    r = client.post("/inbox/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# ── create_from_inbox ────────────────────────────────────────────────────────

def test_create_from_inbox_returns_201(client: TestClient, company_id: str):
    msg = _post_inbox(client)
    r = client.post(f"/quote-preparations/from-inbox/{msg['id']}")
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["status"] == "draft"
    assert data["active"] is True
    assert data["company_id"] == company_id
    assert data["inbox_message_id"] == msg["id"]


def test_create_from_inbox_populates_contact(client: TestClient):
    msg = _post_inbox(client)
    data = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert data["customer_name"] == "Lars Jensen"
    assert data["customer_email"] == "lars@example.com"


def test_create_from_inbox_extracts_address(client: TestClient):
    msg = _post_inbox(client)
    data = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert data["address"] is not None
    assert "2900" in data["address"]


def test_create_from_inbox_detects_task_type(client: TestClient):
    msg = _post_inbox(client)
    data = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert data["task_type"] is not None


def test_create_from_inbox_generates_suggested_lines(client: TestClient):
    msg = _post_inbox(client)
    data = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert isinstance(data["suggested_lines"], list)
    assert len(data["suggested_lines"]) > 0
    assert data["suggested_lines"][0]["description"] == "Besigtigelse og opmåling"


def test_create_from_inbox_generates_missing_info(client: TestClient):
    msg = _post_inbox(client)
    data = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert isinstance(data["missing_info"], list)


def test_create_from_inbox_idempotent(client: TestClient):
    msg = _post_inbox(client)
    r1 = client.post(f"/quote-preparations/from-inbox/{msg['id']}")
    r2 = client.post(f"/quote-preparations/from-inbox/{msg['id']}")
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


def test_create_from_inbox_unknown_message_returns_404(client: TestClient):
    r = client.post("/quote-preparations/from-inbox/ukendt")
    assert r.status_code == 404


def test_create_from_inbox_phone_in_body(client: TestClient):
    msg = _post_inbox(client, body="Ring til mig på 40506070 ang. tilbud.")
    data = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert data["customer_phone"] == "40506070"


# ── company isolation ─────────────────────────────────────────────────────────

def test_company_isolation(client: TestClient, company_id: str):
    # All preparations are scoped to the session company
    msg1 = _post_inbox(client)
    msg2 = _post_inbox(client)
    client.post(f"/quote-preparations/from-inbox/{msg1['id']}")
    client.post(f"/quote-preparations/from-inbox/{msg2['id']}")
    r = client.get("/quote-preparations/")
    assert all(p["company_id"] == company_id for p in r.json())
    assert len(r.json()) == 2


# ── list / get ───────────────────────────────────────────────────────────────

def test_list_preparations(client: TestClient):
    msg1 = _post_inbox(client)
    msg2 = _post_inbox(client)
    client.post(f"/quote-preparations/from-inbox/{msg1['id']}")
    client.post(f"/quote-preparations/from-inbox/{msg2['id']}")
    r = client.get("/quote-preparations/")
    assert len(r.json()) == 2


def test_filter_by_status(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    client.post(f"/quote-preparations/{qp['id']}/review")
    r = client.get("/quote-preparations/?status=reviewed")
    assert len(r.json()) == 1
    assert r.json()[0]["status"] == "reviewed"


def test_get_not_found(client: TestClient):
    assert client.get("/quote-preparations/ukendt").status_code == 404


# ── update ───────────────────────────────────────────────────────────────────

def test_update_draft(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    r = client.patch(f"/quote-preparations/{qp['id']}", json={
        "customer_name": "Mette Nielsen",
        "address": "Nørregade 1, 1165 København K",
    })
    assert r.status_code == 200
    assert r.json()["customer_name"] == "Mette Nielsen"
    assert r.json()["address"] == "Nørregade 1, 1165 København K"


def test_update_suggested_lines(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    new_lines = [{"description": "Specialbehandling", "unit": "stk", "quantity": 2, "unit_price": 500.0, "notes": ""}]
    r = client.patch(f"/quote-preparations/{qp['id']}", json={"suggested_lines": new_lines})
    assert r.status_code == 200
    assert r.json()["suggested_lines"][0]["description"] == "Specialbehandling"


def test_update_converted_rejected(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    client.post(f"/quote-preparations/{qp['id']}/convert-to-flow")
    r = client.patch(f"/quote-preparations/{qp['id']}", json={"address": "Ny adresse"})
    assert r.status_code == 409


# ── status transitions ────────────────────────────────────────────────────────

def test_review_transition(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    r = client.post(f"/quote-preparations/{qp['id']}/review")
    assert r.status_code == 200
    assert r.json()["status"] == "reviewed"


def test_review_already_converted_rejected(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    client.post(f"/quote-preparations/{qp['id']}/convert-to-flow")
    r = client.post(f"/quote-preparations/{qp['id']}/review")
    assert r.status_code == 409


def test_review_not_found(client: TestClient):
    assert client.post("/quote-preparations/ukendt/review").status_code == 404


# ── convert-to-flow ───────────────────────────────────────────────────────────

def test_convert_creates_customer_enquiry_project_quote(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    r = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow")
    assert r.status_code == 201, r.json()
    result = r.json()
    assert result["customer_id"] is not None
    assert result["enquiry_id"] is not None
    assert result["project_id"] is not None
    assert result["quote_id"] is not None


def test_convert_links_back_to_preparation(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    result = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow").json()
    updated_qp = client.get(f"/quote-preparations/{qp['id']}").json()
    assert updated_qp["status"] == "converted"
    assert updated_qp["enquiry_id"] == result["enquiry_id"]
    assert updated_qp["project_id"] == result["project_id"]
    assert updated_qp["quote_id"] == result["quote_id"]


def test_convert_creates_quote_with_lines(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    result = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow").json()
    quote = client.get(f"/quotes/{result['quote_id']}").json()
    assert quote["status"] == "draft"
    assert len(quote["lines"]) > 0


def test_convert_customer_belongs_to_company(client: TestClient, company_id: str):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    result = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow").json()
    customer = client.get(f"/customers/{result['customer_id']}").json()
    assert customer["company_id"] == company_id


def test_convert_enquiry_is_qualified(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    result = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow").json()
    enquiry = client.get(f"/enquiries/{result['enquiry_id']}").json()
    assert enquiry["status"] == "qualified"


def test_convert_project_is_draft(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    result = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow").json()
    project = client.get(f"/projects/{result['project_id']}").json()
    assert project["status"] == "draft"


def test_convert_already_converted_idempotent(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    r1 = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow").json()
    r2 = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow").json()
    assert r1["quote_id"] == r2["quote_id"]
    assert r1["project_id"] == r2["project_id"]


def test_convert_without_customer_name_rejected(client: TestClient):
    msg = _post_inbox(client, sender_name=None)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    r = client.post(f"/quote-preparations/{qp['id']}/convert-to-flow")
    assert r.status_code == 422


def test_convert_archived_reviewed_then_convert(client: TestClient):
    msg = _post_inbox(client)
    qp_id = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()["id"]
    r_review = client.post(f"/quote-preparations/{qp_id}/review")
    assert r_review.status_code == 200
    r_convert = client.post(f"/quote-preparations/{qp_id}/convert-to-flow")
    assert r_convert.status_code == 201


def test_convert_not_found(client: TestClient):
    assert client.post("/quote-preparations/ukendt/convert-to-flow").status_code == 404


# ── missing info generation ───────────────────────────────────────────────────

def test_missing_info_no_address(client: TestClient):
    msg = _post_inbox(
        client,
        subject="Malerarbejde",
        body="Hej, jeg vil gerne have maling i min lejlighed.",
    )
    data = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert any("adresse" in item.lower() or "lokation" in item.lower() for item in data["missing_info"])


def test_missing_info_includes_photos_when_absent(client: TestClient):
    msg = _post_inbox(
        client,
        subject="Tilbud ønskes",
        body="Maling af hus ønsket.",
    )
    data = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert any("foto" in item.lower() or "billede" in item.lower() for item in data["missing_info"])


# ── soft-delete ───────────────────────────────────────────────────────────────

def test_soft_delete(client: TestClient):
    msg = _post_inbox(client)
    qp = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()
    assert client.delete(f"/quote-preparations/{qp['id']}").status_code == 204
    assert all(p["id"] != qp["id"] for p in client.get("/quote-preparations/").json())
    direct = client.get(f"/quote-preparations/{qp['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


# ── convert-to-flow: source and send_email ────────────────────────────────────


def _make_qp(client: TestClient, *, email: Optional[str] = "lars@example.com") -> str:
    """Create a QuotePreparation with given customer email and return its id."""
    msg = _post_inbox(client)
    qp_id = client.post(f"/quote-preparations/from-inbox/{msg['id']}").json()["id"]
    # Patch customer_email to the desired value via PATCH
    client.patch(f"/quote-preparations/{qp_id}", json={"customer_email": email})
    return qp_id


def test_convert_to_flow_default_source(client: TestClient, session):
    """Empty body → 201, created Enquiry has source == 'email'."""
    from haandvaerker.models.enquiry import Enquiry
    qp_id = _make_qp(client)
    r = client.post(f"/quote-preparations/{qp_id}/convert-to-flow")
    assert r.status_code == 201, r.json()
    result = r.json()
    enquiry = session.get(Enquiry, result["enquiry_id"])
    assert enquiry is not None
    assert enquiry.source.value == "email"


def test_convert_to_flow_phone_source(client: TestClient, session):
    """Body with source='phone' → 201, Enquiry has source == 'phone'."""
    from haandvaerker.models.enquiry import Enquiry
    qp_id = _make_qp(client)
    r = client.post(f"/quote-preparations/{qp_id}/convert-to-flow", json={"source": "phone"})
    assert r.status_code == 201, r.json()
    result = r.json()
    enquiry = session.get(Enquiry, result["enquiry_id"])
    assert enquiry is not None
    assert enquiry.source.value == "phone"


def test_convert_to_flow_invalid_source(client: TestClient):
    """Body with source='fax' → 422 (invalid enum value)."""
    qp_id = _make_qp(client)
    r = client.post(f"/quote-preparations/{qp_id}/convert-to-flow", json={"source": "fax"})
    assert r.status_code == 422, r.json()


def test_convert_to_flow_send_email_success(client: TestClient):
    """send_email=True, customer has email, SMTP mocked to succeed → 201, email_sent=True."""
    qp_id = _make_qp(client, email="lars@example.com")
    with patch(
        "haandvaerker.services.wizard_service.is_smtp_configured", return_value=True
    ), patch(
        "haandvaerker.services.wizard_service.send_email", return_value=None
    ):
        r = client.post(
            f"/quote-preparations/{qp_id}/convert-to-flow",
            json={"send_email": True, "email_subject": "Tak", "email_body": "Vi har modtaget din henvendelse."},
        )
    assert r.status_code == 201, r.json()
    result = r.json()
    assert result["email_sent"] is True
    assert result["email_error"] is None
    assert result["customer_id"] is not None
    assert result["enquiry_id"] is not None
    assert result["project_id"] is not None
    assert result["quote_id"] is not None


def test_convert_to_flow_send_email_smtp_error(client: TestClient, session):
    """SMTP raises SmtpSendError → 201, email_sent=False, entities still in DB."""
    from haandvaerker.models.customer import Customer
    from haandvaerker.services.smtp_sender import SmtpSendError
    qp_id = _make_qp(client, email="lars@example.com")
    with patch(
        "haandvaerker.services.wizard_service.is_smtp_configured", return_value=True
    ), patch(
        "haandvaerker.services.wizard_service.send_email",
        side_effect=SmtpSendError("connection refused"),
    ):
        r = client.post(
            f"/quote-preparations/{qp_id}/convert-to-flow",
            json={"send_email": True},
        )
    assert r.status_code == 201, r.json()
    result = r.json()
    assert result["email_sent"] is False
    assert result["email_error"] is not None and len(result["email_error"]) > 0
    # Entities must still exist in DB
    assert session.get(Customer, result["customer_id"]) is not None


def test_convert_to_flow_send_email_no_customer_email(client: TestClient):
    """send_email=True but customer has no email → 201, email_sent=False, error mentions email."""
    qp_id = _make_qp(client, email=None)
    r = client.post(
        f"/quote-preparations/{qp_id}/convert-to-flow",
        json={"send_email": True},
    )
    assert r.status_code == 201, r.json()
    result = r.json()
    assert result["email_sent"] is False
    assert result["email_error"] is not None
    assert "email" in result["email_error"].lower()
