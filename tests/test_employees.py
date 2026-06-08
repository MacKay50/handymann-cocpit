from fastapi.testclient import TestClient


def test_create_employee(client: TestClient, company_id: str):
    r = client.post("/employees/", json={"name": "Lars Nielsen", "default_hourly_rate": 650.0})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Lars Nielsen"
    assert data["default_hourly_rate"] == 650.0
    assert data["company_id"] == company_id
    assert data["active"] is True
    assert "cpr_number" not in data


def test_cpr_is_masked(client: TestClient):
    r = client.post("/employees/", json={
        "name": "Mette Hansen", "default_hourly_rate": 580.0,
        "cpr_number": "010190-1234",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["cpr_masked"] == "****1234"
    assert "cpr_number" not in data


def test_cpr_none_when_not_set(client: TestClient):
    r = client.post("/employees/", json={"name": "Ingen CPR", "default_hourly_rate": 500.0})
    assert r.status_code == 201
    assert r.json()["cpr_masked"] is None


def test_create_employee_rate_required(client: TestClient):
    # Missing required field → 422
    r = client.post("/employees/", json={"name": "Test"})
    assert r.status_code == 422


def test_list_employees(client: TestClient):
    client.post("/employees/", json={"name": "A", "default_hourly_rate": 600.0})
    client.post("/employees/", json={"name": "B", "default_hourly_rate": 700.0})
    r = client.get("/employees/")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_employees_filter_returns_session_company_only(client: TestClient):
    # List returns only session company's employees
    client.post("/employees/", json={"name": "A", "default_hourly_rate": 600.0})
    r = client.get("/employees/")
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "A"


def test_get_employee(client: TestClient):
    create = client.post("/employees/", json={"name": "Test", "default_hourly_rate": 600.0})
    eid = create.json()["id"]
    r = client.get(f"/employees/{eid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Test"


def test_update_employee(client: TestClient):
    create = client.post("/employees/", json={"name": "Gammel", "default_hourly_rate": 600.0})
    eid = create.json()["id"]
    r = client.patch(f"/employees/{eid}", json={"name": "Ny", "default_hourly_rate": 700.0})
    assert r.status_code == 200
    assert r.json()["name"] == "Ny"
    assert r.json()["default_hourly_rate"] == 700.0


def test_deactivate_employee(client: TestClient):
    create = client.post("/employees/", json={"name": "Til Sletning", "default_hourly_rate": 600.0})
    eid = create.json()["id"]
    r = client.delete(f"/employees/{eid}")
    assert r.status_code == 204
    active = client.get("/employees/")
    assert all(e["id"] != eid for e in active.json())
