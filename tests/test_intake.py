"""Tests for POST /intake dispatcher (Phase 3)."""
from fastapi.testclient import TestClient


def _make_project(client: TestClient) -> str:
    cid = client.post("/customers/", json={"name": "Intake Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"customer_id": cid, "title": "Intake Projekt"}).json()["id"]
    return pid


# --- type=message ---

def test_intake_message_creates_inbox_message(client: TestClient):
    r = client.post("/intake/", json={
        "type": "message",
        "source": "email",
        "sender_name": "Test Afsender",
        "subject": "Hej",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "message"
    assert "id" in body
    assert isinstance(body["id"], str)


def test_intake_message_company_id_not_in_response(client: TestClient):
    """company_id must never appear in the response body."""
    r = client.post("/intake/", json={
        "type": "message",
        "source": "phone",
    })
    assert r.status_code == 201
    assert "company_id" not in r.json()


def test_intake_message_stored_in_inbox(client: TestClient):
    r = client.post("/intake/", json={
        "type": "message",
        "source": "website",
        "sender_name": "Web Kunde",
        "subject": "Forespørgsel",
    })
    assert r.status_code == 201
    msg_id = r.json()["id"]
    inbox = client.get("/inbox/").json()
    assert any(m["id"] == msg_id for m in inbox)


# --- type=project_task ---

def test_intake_project_task_creates_action_item(client: TestClient):
    pid = _make_project(client)
    r = client.post("/intake/", json={
        "type": "project_task",
        "project_id": pid,
        "title": "Sæt primer op",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "project_task"
    assert "id" in body


def test_intake_project_task_linked_to_project(client: TestClient):
    pid = _make_project(client)
    r = client.post("/intake/", json={
        "type": "project_task",
        "project_id": pid,
        "title": "Opgave tilknyttet projekt",
    })
    assert r.status_code == 201
    item_id = r.json()["id"]
    items = client.get(f"/action-items/?project_id={pid}").json()
    assert any(i["id"] == item_id for i in items)


def test_intake_project_task_unknown_project_rejected(client: TestClient):
    r = client.post("/intake/", json={
        "type": "project_task",
        "project_id": "ukendt-projekt",
        "title": "Opgave",
    })
    assert r.status_code == 422


# --- type=internal_task ---

def test_intake_internal_task_creates_action_item_without_project(client: TestClient):
    r = client.post("/intake/", json={
        "type": "internal_task",
        "title": "Intern administrationsopgave",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "internal_task"
    assert "id" in body


def test_intake_internal_task_has_no_project(client: TestClient):
    r = client.post("/intake/", json={
        "type": "internal_task",
        "title": "Intern opgave uden projekt",
    })
    assert r.status_code == 201
    item_id = r.json()["id"]
    item = client.get(f"/action-items/{item_id}").json()
    assert item["project_id"] is None
