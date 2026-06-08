from __future__ import annotations
from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    cid = client.post("/companies/", json={"name": "Test Firma"}).json()["id"]
    return {"company_id": cid}


def _create_comm(client: TestClient, company_id: str, **extra) -> dict:
    payload = {
        "company_id": company_id,
        "communication_type": "inbound_email",
        "summary": "Kunde spørger om status",
        "body": "Hej, hvad er status på vores projekt?",
        **extra,
    }
    r = client.post("/project-communications/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# ── create ────────────────────────────────────────────────────────────────────

def test_create_communication_returns_201(client: TestClient):
    ctx = _setup(client)
    data = _create_comm(client, ctx["company_id"])
    assert data["communication_type"] == "inbound_email"
    assert data["summary"] == "Kunde spørger om status"
    assert data["priority"] == "normal"
    assert data["active"] is True


def test_create_with_high_priority(client: TestClient):
    ctx = _setup(client)
    data = _create_comm(client, ctx["company_id"], priority="high", requires_action=True)
    assert data["priority"] == "high"
    assert data["requires_action"] is True


# ── list / get ────────────────────────────────────────────────────────────────

def test_list_empty(client: TestClient):
    r = client.get("/project-communications/")
    assert r.status_code == 200
    assert r.json() == []


def test_list_by_company(client: TestClient):
    ctx = _setup(client)
    _create_comm(client, ctx["company_id"])
    _create_comm(client, ctx["company_id"])
    r = client.get("/project-communications/", params={"company_id": ctx["company_id"]})
    assert len(r.json()) == 2


def test_get_not_found(client: TestClient):
    r = client.get("/project-communications/nonexistent")
    assert r.status_code == 404


# ── update ────────────────────────────────────────────────────────────────────

def test_update_summary(client: TestClient):
    ctx = _setup(client)
    comm = _create_comm(client, ctx["company_id"])
    r = client.patch(f"/project-communications/{comm['id']}", json={"summary": "Opdateret opsummering"})
    assert r.status_code == 200
    assert r.json()["summary"] == "Opdateret opsummering"


def test_update_priority(client: TestClient):
    ctx = _setup(client)
    comm = _create_comm(client, ctx["company_id"])
    r = client.patch(f"/project-communications/{comm['id']}", json={"priority": "urgent"})
    assert r.status_code == 200
    assert r.json()["priority"] == "urgent"


# ── delete ────────────────────────────────────────────────────────────────────

def test_soft_delete(client: TestClient):
    ctx = _setup(client)
    comm = _create_comm(client, ctx["company_id"])
    r = client.delete(f"/project-communications/{comm['id']}")
    assert r.status_code == 204
    r2 = client.get("/project-communications/", params={"company_id": ctx["company_id"]})
    assert all(c["id"] != comm["id"] for c in r2.json())


# ── project link ──────────────────────────────────────────────────────────────

def test_filter_by_project(client: TestClient):
    ctx = _setup(client)
    # Create a project to link to
    cust = client.post("/customers/", json={"company_id": ctx["company_id"], "name": "Test Kunde"}).json()
    proj = client.post("/projects/", json={
        "company_id": ctx["company_id"],
        "customer_id": cust["id"],
        "title": "Malerprojekt",
        "status": "draft",
    }).json()
    comm = _create_comm(client, ctx["company_id"], project_id=proj["id"])
    assert comm["project_id"] == proj["id"]
    r = client.get("/project-communications/", params={"project_id": proj["id"]})
    assert any(c["id"] == comm["id"] for c in r.json())
