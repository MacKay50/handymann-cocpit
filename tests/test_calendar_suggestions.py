from __future__ import annotations
from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    cid = client.post("/companies/", json={"name": "Test Firma"}).json()["id"]
    return {"company_id": cid}


def _create_suggestion(client: TestClient, company_id: str, **extra) -> dict:
    payload = {
        "company_id": company_id,
        "event_type": "site_visit",
        "title": "Syn på Villa Strandvej",
        "new_start_at": "2026-06-10T10:00:00",
        "end_at": "2026-06-10T11:00:00",
        **extra,
    }
    r = client.post("/calendar-suggestions/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# ── create ────────────────────────────────────────────────────────────────────

def test_create_suggestion_returns_201(client: TestClient):
    ctx = _setup(client)
    data = _create_suggestion(client, ctx["company_id"])
    assert data["status"] == "pending"
    assert data["event_type"] == "site_visit"
    assert data["title"] == "Syn på Villa Strandvej"
    assert data["active"] is True


def test_create_with_location(client: TestClient):
    ctx = _setup(client)
    data = _create_suggestion(client, ctx["company_id"], location="Strandvej 42, 2900 Hellerup")
    assert data["location"] == "Strandvej 42, 2900 Hellerup"


# ── list / get ────────────────────────────────────────────────────────────────

def test_list_empty(client: TestClient):
    r = client.get("/calendar-suggestions/")
    assert r.status_code == 200
    assert r.json() == []


def test_list_by_company(client: TestClient):
    ctx = _setup(client)
    _create_suggestion(client, ctx["company_id"])
    r = client.get("/calendar-suggestions/", params={"company_id": ctx["company_id"]})
    assert len(r.json()) == 1


def test_get_not_found(client: TestClient):
    r = client.get("/calendar-suggestions/nonexistent")
    assert r.status_code == 404


def test_filter_by_status(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    client.post(f"/calendar-suggestions/{s['id']}/approve")
    r = client.get("/calendar-suggestions/", params={"status": "approved"})
    assert any(x["id"] == s["id"] for x in r.json())


# ── approve / reject ──────────────────────────────────────────────────────────

def test_approve_suggestion(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    r = client.post(f"/calendar-suggestions/{s['id']}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_reject_suggestion(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    r = client.post(f"/calendar-suggestions/{s['id']}/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_cannot_approve_already_rejected(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    client.post(f"/calendar-suggestions/{s['id']}/reject")
    r = client.post(f"/calendar-suggestions/{s['id']}/approve")
    assert r.status_code == 409


# ── apply (creates Appointment) ───────────────────────────────────────────────

def test_apply_creates_appointment(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    client.post(f"/calendar-suggestions/{s['id']}/approve")
    r = client.post(f"/calendar-suggestions/{s['id']}/apply")
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "applied"
    assert data["appointment_id"] is not None


def test_apply_without_approval_returns_409(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    r = client.post(f"/calendar-suggestions/{s['id']}/apply")
    assert r.status_code == 409


def test_apply_without_start_time_returns_422(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"], new_start_at=None)
    client.post(f"/calendar-suggestions/{s['id']}/approve")
    r = client.post(f"/calendar-suggestions/{s['id']}/apply")
    assert r.status_code == 422


def test_appointment_accessible_after_apply(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    client.post(f"/calendar-suggestions/{s['id']}/approve")
    applied = client.post(f"/calendar-suggestions/{s['id']}/apply").json()
    apt_r = client.get(f"/appointments/{applied['appointment_id']}")
    assert apt_r.status_code == 200
    apt = apt_r.json()
    assert apt["appointment_type"] == "site_visit"


# ── update / delete ───────────────────────────────────────────────────────────

def test_update_title(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    r = client.patch(f"/calendar-suggestions/{s['id']}", json={"title": "Nyt besøg"})
    assert r.status_code == 200
    assert r.json()["title"] == "Nyt besøg"


def test_cannot_edit_applied(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    client.post(f"/calendar-suggestions/{s['id']}/approve")
    client.post(f"/calendar-suggestions/{s['id']}/apply")
    r = client.patch(f"/calendar-suggestions/{s['id']}", json={"title": "Too late"})
    assert r.status_code == 409


def test_soft_delete(client: TestClient):
    ctx = _setup(client)
    s = _create_suggestion(client, ctx["company_id"])
    r = client.delete(f"/calendar-suggestions/{s['id']}")
    assert r.status_code == 204
    r2 = client.get("/calendar-suggestions/", params={"company_id": ctx["company_id"]})
    assert all(x["id"] != s["id"] for x in r2.json())
