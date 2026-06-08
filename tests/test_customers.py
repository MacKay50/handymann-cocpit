from fastapi.testclient import TestClient


def test_create_customer(client: TestClient, company_id: str):
    resp = client.post("/customers/", json={"name": "Maler Hansen ApS", "phone": "12345678"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Maler Hansen ApS"
    assert data["company_id"] == company_id
    assert "id" in data
    assert "cvr_number" not in data  # rå CVR må ikke returneres


def test_cvr_is_masked(client: TestClient):
    resp = client.post("/customers/", json={"name": "Tømrer Jensen", "cvr_number": "12345678"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["cvr_masked"] == "****5678"
    assert "cvr_number" not in data


def test_list_customers(client: TestClient):
    client.post("/customers/", json={"name": "Kunde A"})
    client.post("/customers/", json={"name": "Kunde B"})
    resp = client.get("/customers/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_customers_returns_session_company_only(client: TestClient, company_id: str):
    # Only the session company's customers are returned
    client.post("/customers/", json={"name": "Kunde A"})
    r = client.get("/customers/")
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "Kunde A"
    assert r.json()[0]["company_id"] == company_id


def test_get_customer_not_found(client: TestClient):
    resp = client.get("/customers/nonexistent-id")
    assert resp.status_code == 404


def test_update_customer(client: TestClient):
    create = client.post("/customers/", json={"name": "Gammel Navn"})
    cid = create.json()["id"]
    resp = client.patch(f"/customers/{cid}", json={"name": "Nyt Navn"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Nyt Navn"


def test_deactivate_customer(client: TestClient):
    create = client.post("/customers/", json={"name": "Til Sletning"})
    cid = create.json()["id"]
    resp = client.delete(f"/customers/{cid}")
    assert resp.status_code == 204
    active = client.get("/customers/")
    assert all(c["id"] != cid for c in active.json())
    direct = client.get(f"/customers/{cid}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


def test_duplicate_id_rejected(client: TestClient):
    client.post("/customers/", json={"id": "fixed-id", "name": "Original"})
    resp = client.post("/customers/", json={"id": "fixed-id", "name": "Duplikat"})
    assert resp.status_code == 409
