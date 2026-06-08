from __future__ import annotations

from fastapi.testclient import TestClient


def _create_customer(client: TestClient, company_id: str, name: str = "Test Kunde") -> dict:
    r = client.post("/customers/", json={"name": name, "company_id": company_id})
    assert r.status_code == 201, r.json()
    return r.json()


def _create_project(client: TestClient, customer_id: str, title: str, address: str) -> dict:
    r = client.post("/projects/", json={
        "title": title,
        "customer_id": customer_id,
        "address": address,
    })
    assert r.status_code == 201, r.json()
    return r.json()


def test_address_history_matches_projects(client: TestClient, company_id: str) -> None:
    customer = _create_customer(client, company_id)
    cid = customer["id"]
    _create_project(client, cid, "Maleopgave", "Bredgade 12, 1260 København")

    r = client.get(f"/customers/{cid}/address-history?address=Bredgade")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert "projects" in data
    assert "historical_offers" in data
    matching = [p for p in data["projects"] if "Bredgade" in (p.get("address") or "")]
    assert len(matching) >= 1


def test_address_history_case_insensitive(client: TestClient, company_id: str) -> None:
    # Use ASCII-only address — SQLite lower() only handles ASCII, not Danish chars
    customer = _create_customer(client, company_id)
    cid = customer["id"]
    _create_project(client, cid, "Opgave", "VESTERGADE 8")

    r = client.get(f"/customers/{cid}/address-history?address=vestergade")
    assert r.status_code == 200, r.json()
    data = r.json()
    matching = [p for p in data["projects"] if p.get("address") == "VESTERGADE 8"]
    assert len(matching) >= 1


def test_address_history_customer_not_found(client: TestClient, company_id: str) -> None:
    r = client.get("/customers/nonexistent/address-history?address=test")
    assert r.status_code == 404, r.json()
