from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from haandvaerker.models.project import Project


def _create_customer(client: TestClient, company_id: str, name: str = "Test Kunde") -> dict:
    r = client.post("/customers/", json={"name": name, "company_id": company_id})
    assert r.status_code == 201, r.json()
    return r.json()


def test_repeat_job_creates_project_and_quote(client: TestClient, company_id: str) -> None:
    customer = _create_customer(client, company_id)
    cid = customer["id"]

    r = client.post(f"/customers/{cid}/repeat-job?title=Maler+opgave")
    assert r.status_code == 201, r.json()
    data = r.json()
    assert "project" in data
    assert "quote" in data
    assert "id" in data["project"]
    assert "id" in data["quote"]
    assert data["quote"]["title"] == "Maler opgave"
    assert data["project"]["customer_id"] == cid


def test_repeat_job_inactive_customer(client: TestClient, company_id: str) -> None:
    customer = _create_customer(client, company_id, name="Inaktiv Kunde")
    cid = customer["id"]

    # Soft-delete customer
    del_r = client.delete(f"/customers/{cid}")
    assert del_r.status_code == 204

    r = client.post(f"/customers/{cid}/repeat-job?title=Test")
    assert r.status_code == 422, r.json()
    assert "inaktiv" in r.json()["detail"].lower()


def test_repeat_job_missing_customer(client: TestClient, company_id: str) -> None:
    r = client.post("/customers/nonexistent/repeat-job?title=Test")
    assert r.status_code == 404, r.json()


def test_repeat_job_empty_title(client: TestClient, session: Session, company_id: str) -> None:
    customer = _create_customer(client, company_id)
    cid = customer["id"]

    projects_before = session.exec(select(Project).where(Project.customer_id == cid)).all()

    r = client.post(f"/customers/{cid}/repeat-job?title=")
    assert r.status_code == 422, r.json()

    # AC-3: no orphaned Project must exist after the failed request (R3.RISK-06)
    projects_after = session.exec(select(Project).where(Project.customer_id == cid)).all()
    assert len(projects_after) == len(projects_before)
