from __future__ import annotations
from fastapi.testclient import TestClient


def _post_inbox(client: TestClient, subject="Tilbud på maling", body="Ønsker tilbud på maling af villa") -> dict:
    r = client.post("/inbox/", json={
        "source": "email",
        "received_at": "2026-05-20T10:00:00",
        "sender_name": "Test Person",
        "sender_email": "test@test.dk",
        "subject": subject,
        "body": body,
    })
    assert r.status_code == 201, r.json()
    return r.json()


# ── classify endpoint ─────────────────────────────────────────────────────────

def test_classify_inbox_message_returns_201(client: TestClient, company_id: str):
    msg = _post_inbox(client)
    r = client.post(f"/message-classifications/classify/{msg['id']}")
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["inbox_message_id"] == msg["id"]
    assert data["company_id"] == company_id
    assert data["primary_category"] is not None


def test_classify_quote_request_detected(client: TestClient):
    msg = _post_inbox(client, subject="Forespørgsel tilbud", body="Vi ønsker tilbud på maling")
    data = client.post(f"/message-classifications/classify/{msg['id']}").json()
    assert data["primary_category"] == "new_quote_request"
    assert data["is_quote_related"] is True


def test_classify_idempotent(client: TestClient):
    msg = _post_inbox(client)
    r1 = client.post(f"/message-classifications/classify/{msg['id']}").json()
    r2 = client.post(f"/message-classifications/classify/{msg['id']}").json()
    assert r1["id"] == r2["id"]


def test_classify_inbox_not_found(client: TestClient):
    r = client.post("/message-classifications/classify/nonexistent")
    assert r.status_code == 404


def test_classification_includes_entities(client: TestClient):
    msg = _post_inbox(client, body="Ring til mig på 23 45 67 89, email lars@example.com")
    data = client.post(f"/message-classifications/classify/{msg['id']}").json()
    assert isinstance(data["entities"], list)
    entity_types = [e["entity_type"] for e in data["entities"]]
    assert "phone" in entity_types or "email" in entity_types


# ── list / get ────────────────────────────────────────────────────────────────

def test_list_classifications_empty(client: TestClient):
    r = client.get("/message-classifications/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_classifications_after_classify(client: TestClient):
    msg = _post_inbox(client)
    client.post(f"/message-classifications/classify/{msg['id']}")
    r = client.get("/message-classifications/")
    assert len(r.json()) == 1


def test_get_classification_not_found(client: TestClient):
    r = client.get("/message-classifications/nonexistent")
    assert r.status_code == 404


# ── manual override ───────────────────────────────────────────────────────────

def test_override_classification(client: TestClient):
    msg = _post_inbox(client)
    mc = client.post(f"/message-classifications/classify/{msg['id']}").json()
    r = client.patch(f"/message-classifications/{mc['id']}", json={"primary_category": "complaint"})
    assert r.status_code == 200
    data = r.json()
    assert data["primary_category"] == "complaint"
    assert data["user_overridden"] is True
    assert data["classification_source"] == "manual"


def test_classification_requires_action_complaint(client: TestClient):
    msg = _post_inbox(
        client,
        subject="Klage",
        body="Vi klager over arbejdet, vi er utilfredse med resultatet"
    )
    data = client.post(f"/message-classifications/classify/{msg['id']}").json()
    assert data["requires_action"] is True
    assert data["priority"] >= 2
