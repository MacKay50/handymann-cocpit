import uuid
from fastapi.testclient import TestClient


def _make_customer(client: TestClient, name: str = "Test Kunde") -> str:
    vid = client.post("/companies/", json={"name": "Test Firma"}).json()["id"]
    resp = client.post("/customers/", json={"name": name, "company_id": vid})
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_project(client: TestClient):
    cid = _make_customer(client)
    resp = client.post("/projects/", json={"title": "Køkkenrenovering", "customer_id": cid})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Køkkenrenovering"
    assert data["customer_id"] == cid
    assert data["status"] == "draft"
    assert data["active"] is True
    assert "id" in data


def test_create_project_unknown_customer(client: TestClient):
    resp = client.post("/projects/", json={"title": "Test", "customer_id": "ukendt-id"})
    assert resp.status_code == 422


def test_create_project_inactive_customer(client: TestClient):
    cid = _make_customer(client, "Inaktiv Kunde")
    client.delete(f"/customers/{cid}")
    resp = client.post("/projects/", json={"title": "Test", "customer_id": cid})
    assert resp.status_code == 422


def test_create_project_missing_customer_id(client: TestClient):
    resp = client.post("/projects/", json={"title": "Intet kunde-id"})
    assert resp.status_code == 422


def test_list_projects(client: TestClient):
    cid = _make_customer(client)
    client.post("/projects/", json={"title": "Projekt A", "customer_id": cid})
    client.post("/projects/", json={"title": "Projekt B", "customer_id": cid})
    resp = client.get("/projects/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_projects_filter_by_customer(client: TestClient):
    cid1 = _make_customer(client, "Kunde 1")
    cid2 = _make_customer(client, "Kunde 2")
    client.post("/projects/", json={"title": "P1", "customer_id": cid1})
    client.post("/projects/", json={"title": "P2", "customer_id": cid2})
    resp = client.get(f"/projects/?customer_id={cid1}")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["title"] == "P1"


def test_list_projects_filter_by_status(client: TestClient):
    cid = _make_customer(client)
    client.post("/projects/", json={"title": "Kladde", "customer_id": cid, "status": "draft"})
    client.post("/projects/", json={"title": "Aktiv", "customer_id": cid, "status": "active"})
    resp = client.get("/projects/?status=active")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["title"] == "Aktiv"


def test_get_project(client: TestClient):
    cid = _make_customer(client)
    create = client.post("/projects/", json={"title": "Badrum", "customer_id": cid})
    pid = create.json()["id"]
    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Badrum"


def test_get_project_not_found(client: TestClient):
    resp = client.get("/projects/ukendt-id")
    assert resp.status_code == 404


def test_update_project(client: TestClient):
    cid = _make_customer(client)
    create = client.post("/projects/", json={"title": "Gammel titel", "customer_id": cid})
    pid = create.json()["id"]
    resp = client.patch(f"/projects/{pid}", json={"title": "Ny titel", "status": "active"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Ny titel"
    assert data["status"] == "active"


def test_deactivate_project(client: TestClient):
    cid = _make_customer(client)
    create = client.post("/projects/", json={"title": "Skal deaktiveres", "customer_id": cid})
    pid = create.json()["id"]
    resp = client.delete(f"/projects/{pid}")
    assert resp.status_code == 204
    # Vises ikke i aktiv-liste
    active = client.get("/projects/")
    assert all(p["id"] != pid for p in active.json())
    # Stadig tilgængeligt direkte
    direct = client.get(f"/projects/{pid}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


def test_duplicate_project_id_rejected(client: TestClient):
    cid = _make_customer(client)
    fixed_id = str(uuid.uuid4())
    client.post("/projects/", json={"id": fixed_id, "title": "Original", "customer_id": cid})
    resp = client.post("/projects/", json={"id": fixed_id, "title": "Duplikat", "customer_id": cid})
    assert resp.status_code == 409
