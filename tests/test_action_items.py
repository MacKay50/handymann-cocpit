from __future__ import annotations
from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    cid = client.post("/companies/", json={"name": "Test Firma"}).json()["id"]
    return {"company_id": cid}


def _create_item(client: TestClient, company_id: str, **extra) -> dict:
    payload = {"company_id": company_id, "title": "Ring tilbage til kunde", **extra}
    r = client.post("/action-items/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# ── create ────────────────────────────────────────────────────────────────────

def test_create_action_item_returns_201(client: TestClient):
    ctx = _setup(client)
    data = _create_item(client, ctx["company_id"])
    assert data["title"] == "Ring tilbage til kunde"
    assert data["status"] == "open"
    assert data["priority"] == "normal"
    assert data["active"] is True


def test_create_with_due_date(client: TestClient):
    ctx = _setup(client)
    data = _create_item(client, ctx["company_id"], due_at="2026-06-01T12:00:00")
    assert data["due_at"] is not None


def test_create_with_high_priority(client: TestClient):
    ctx = _setup(client)
    data = _create_item(client, ctx["company_id"], priority="high")
    assert data["priority"] == "high"


# ── list / get ────────────────────────────────────────────────────────────────

def test_list_empty(client: TestClient):
    r = client.get("/action-items/")
    assert r.status_code == 200
    assert r.json() == []


def test_list_by_company(client: TestClient):
    ctx = _setup(client)
    _create_item(client, ctx["company_id"])
    _create_item(client, ctx["company_id"])
    r = client.get("/action-items/", params={"company_id": ctx["company_id"]})
    assert len(r.json()) == 2


def test_get_not_found(client: TestClient):
    r = client.get("/action-items/nonexistent")
    assert r.status_code == 404


def test_list_filter_by_status(client: TestClient):
    ctx = _setup(client)
    item = _create_item(client, ctx["company_id"])
    client.post(f"/action-items/{item['id']}/transition", params={"target_status": "in_progress"})
    r = client.get("/action-items/", params={"company_id": ctx["company_id"], "status": "in_progress"})
    assert len(r.json()) == 1


# ── update ────────────────────────────────────────────────────────────────────

def test_update_title(client: TestClient):
    ctx = _setup(client)
    item = _create_item(client, ctx["company_id"])
    r = client.patch(f"/action-items/{item['id']}", json={"title": "Opdateret opgave"})
    assert r.status_code == 200
    assert r.json()["title"] == "Opdateret opgave"


# ── status transitions ────────────────────────────────────────────────────────

def test_transition_open_to_in_progress(client: TestClient):
    ctx = _setup(client)
    item = _create_item(client, ctx["company_id"])
    r = client.post(f"/action-items/{item['id']}/transition", params={"target_status": "in_progress"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_transition_to_done(client: TestClient):
    ctx = _setup(client)
    item = _create_item(client, ctx["company_id"])
    r = client.post(f"/action-items/{item['id']}/transition", params={"target_status": "done"})
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_invalid_transition_returns_409(client: TestClient):
    ctx = _setup(client)
    item = _create_item(client, ctx["company_id"])
    client.post(f"/action-items/{item['id']}/transition", params={"target_status": "done"})
    r = client.post(f"/action-items/{item['id']}/transition", params={"target_status": "in_progress"})
    assert r.status_code == 409


def test_cancel_from_open(client: TestClient):
    ctx = _setup(client)
    item = _create_item(client, ctx["company_id"])
    r = client.post(f"/action-items/{item['id']}/transition", params={"target_status": "cancelled"})
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


# ── delete ────────────────────────────────────────────────────────────────────

def test_soft_delete(client: TestClient):
    ctx = _setup(client)
    item = _create_item(client, ctx["company_id"])
    r = client.delete(f"/action-items/{item['id']}")
    assert r.status_code == 204
    r2 = client.get("/action-items/", params={"company_id": ctx["company_id"]})
    assert all(i["id"] != item["id"] for i in r2.json())
