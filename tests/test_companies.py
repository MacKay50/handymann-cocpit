from fastapi.testclient import TestClient


def _post_company(client: TestClient, **kwargs) -> dict:
    payload = {"name": "Test Firma AS", **kwargs}
    r = client.post("/companies/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


def test_create_company(client: TestClient):
    data = _post_company(client, phone="12345678", email="info@firma.dk")
    assert data["name"] == "Test Firma AS"
    assert data["active"] is True
    assert "cvr_number" not in data
    assert "id" in data


def test_cvr_is_masked(client: TestClient):
    data = _post_company(client, cvr_number="12345678")
    assert data["cvr_masked"] == "****5678"
    assert "cvr_number" not in data


def test_cvr_none_when_not_set(client: TestClient):
    data = _post_company(client)
    assert data["cvr_masked"] is None


def test_list_companies(client: TestClient, company_id: str):
    # conftest creates 1 company; we create 2 more
    _post_company(client, name="Firma A")
    _post_company(client, name="Firma B")
    r = client.get("/companies/")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert "Firma A" in names
    assert "Firma B" in names


def test_list_active_only(client: TestClient, company_id: str):
    # conftest company + 1 active + 1 inactive
    before = len(client.get("/companies/").json())
    aktiv = _post_company(client, name="Ny Aktiv")
    inaktiv = _post_company(client, name="Inaktiv")
    client.delete(f"/companies/{inaktiv['id']}")
    r = client.get("/companies/")
    # Should be before + 1 (the aktiv one)
    assert len(r.json()) == before + 1
    assert any(c["id"] == aktiv["id"] for c in r.json())
    assert all(c["id"] != inaktiv["id"] for c in r.json())


def test_get_company(client: TestClient):
    data = _post_company(client)
    r = client.get(f"/companies/{data['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Test Firma AS"


def test_get_company_not_found(client: TestClient):
    assert client.get("/companies/ukendt").status_code == 404


def test_update_company(client: TestClient):
    data = _post_company(client, name="Gammelt Navn")
    r = client.patch(f"/companies/{data['id']}", json={"name": "Nyt Navn"})
    assert r.status_code == 200
    assert r.json()["name"] == "Nyt Navn"


def test_update_cvr_returns_masked(client: TestClient):
    data = _post_company(client)
    r = client.patch(f"/companies/{data['id']}", json={"cvr_number": "87654321"})
    assert r.status_code == 200
    assert r.json()["cvr_masked"] == "****4321"
    assert "cvr_number" not in r.json()


def test_deactivate_company(client: TestClient):
    data = _post_company(client)
    assert client.delete(f"/companies/{data['id']}").status_code == 204
    assert all(c["id"] != data["id"] for c in client.get("/companies/").json())
    direct = client.get(f"/companies/{data['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


def test_duplicate_id_rejected(client: TestClient):
    _post_company(client, **{"id": "fixed-id"})
    r = client.post("/companies/", json={"id": "fixed-id", "name": "Duplikat"})
    assert r.status_code == 409
