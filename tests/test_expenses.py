from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str, str]:
    vid = client.post("/companies/", json={"name": "Test Firma"}).json()["id"]
    cid = client.post("/customers/", json={"name": "Kunde", "company_id": vid}).json()["id"]
    pid = client.post("/projects/", json={"title": "Projekt", "customer_id": cid}).json()["id"]
    eid = client.post(
        "/employees/", json={"name": "Lars", "default_hourly_rate": 650.0, "company_id": vid}
    ).json()["id"]
    return cid, pid, eid


def _post_expense(client: TestClient, pid: str, eid: str, **extra) -> dict:
    payload = {"project_id": pid, "employee_id": eid, "date": "2026-05-20", **extra}
    r = client.post("/expenses/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse og beregning ---

def test_create_materialer(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_expense(client, pid, eid, category="materialer", amount_excl_vat=1000.0)
    assert data["category"] == "materialer"
    assert data["amount_excl_vat"] == 1000.0
    assert data["vat_amount"] == 250.0
    assert data["amount_total"] == 1250.0
    assert data["billable"] is True
    assert data["active"] is True
    assert data["km"] is None
    assert data["km_rate"] is None


def test_create_transport_km_default_rate(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_expense(client, pid, eid, category="transport_km", km=100.0)
    assert data["km"] == 100.0
    assert data["km_rate"] == 3.76
    assert data["amount_excl_vat"] == 376.0
    assert data["vat_amount"] == 0.0
    assert data["amount_total"] == 376.0


def test_create_transport_km_custom_rate(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_expense(client, pid, eid, category="transport_km", km=10.0, km_rate=4.0)
    assert data["km_rate"] == 4.0
    assert data["amount_excl_vat"] == 40.0
    assert data["amount_total"] == 40.0


def test_create_transport_km_precision(client: TestClient):
    _, pid, eid = _setup(client)
    # 7 km * 3.76 = 26.32
    data = _post_expense(client, pid, eid, category="transport_km", km=7.0)
    assert data["amount_excl_vat"] == 26.32
    assert data["amount_total"] == 26.32


def test_create_parkering_no_vat_by_default(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_expense(client, pid, eid, category="parkering", amount_excl_vat=50.0)
    assert data["vat_amount"] == 0.0
    assert data["amount_total"] == 50.0


def test_create_andet_no_vat_by_default(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_expense(client, pid, eid, category="andet", amount_excl_vat=200.0)
    assert data["vat_amount"] == 0.0
    assert data["amount_total"] == 200.0


def test_create_parkering_vat_override(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_expense(
        client, pid, eid, category="parkering", amount_excl_vat=50.0, apply_vat=True
    )
    assert data["vat_amount"] == 12.5
    assert data["amount_total"] == 62.5


def test_materialer_vat_override_false(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_expense(
        client, pid, eid, category="materialer", amount_excl_vat=100.0, apply_vat=False
    )
    assert data["vat_amount"] == 0.0
    assert data["amount_total"] == 100.0


# --- Validering ---

def test_create_expense_unknown_project(client: TestClient):
    _, _, eid = _setup(client)
    r = client.post("/expenses/", json={
        "project_id": "ukendt", "employee_id": eid,
        "date": "2026-05-20", "category": "andet", "amount_excl_vat": 10.0,
    })
    assert r.status_code == 422


def test_create_expense_inactive_project(client: TestClient):
    _, pid, eid = _setup(client)
    client.delete(f"/projects/{pid}")
    r = client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "category": "andet", "amount_excl_vat": 10.0,
    })
    assert r.status_code == 422


def test_create_expense_unknown_employee(client: TestClient):
    _, pid, _ = _setup(client)
    r = client.post("/expenses/", json={
        "project_id": pid, "employee_id": "ukendt",
        "date": "2026-05-20", "category": "andet", "amount_excl_vat": 10.0,
    })
    assert r.status_code == 422


def test_create_expense_inactive_employee(client: TestClient):
    _, pid, eid = _setup(client)
    client.delete(f"/employees/{eid}")
    r = client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "category": "andet", "amount_excl_vat": 10.0,
    })
    assert r.status_code == 422


def test_transport_km_missing_km_field(client: TestClient):
    _, pid, eid = _setup(client)
    r = client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "category": "transport_km",
    })
    assert r.status_code == 422


def test_materialer_missing_amount(client: TestClient):
    _, pid, eid = _setup(client)
    r = client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "category": "materialer",
    })
    assert r.status_code == 422


# --- Liste og filtrering ---

def test_list_expenses(client: TestClient):
    _, pid, eid = _setup(client)
    _post_expense(client, pid, eid, category="andet", amount_excl_vat=10.0)
    _post_expense(client, pid, eid, category="parkering", amount_excl_vat=20.0)
    assert len(client.get("/expenses/").json()) == 2


def test_filter_by_project(client: TestClient):
    vid = client.post("/companies/", json={"name": "F"}).json()["id"]
    cid = client.post("/customers/", json={"name": "K", "company_id": vid}).json()["id"]
    pid1 = client.post("/projects/", json={"title": "P1", "customer_id": cid}).json()["id"]
    pid2 = client.post("/projects/", json={"title": "P2", "customer_id": cid}).json()["id"]
    eid = client.post(
        "/employees/", json={"name": "E", "default_hourly_rate": 600.0, "company_id": vid}
    ).json()["id"]
    _post_expense(client, pid1, eid, category="andet", amount_excl_vat=10.0)
    _post_expense(client, pid2, eid, category="andet", amount_excl_vat=20.0)
    r = client.get(f"/expenses/?project_id={pid1}")
    assert len(r.json()) == 1


def test_filter_by_employee(client: TestClient):
    vid = client.post("/companies/", json={"name": "F"}).json()["id"]
    cid = client.post("/customers/", json={"name": "K", "company_id": vid}).json()["id"]
    pid = client.post("/projects/", json={"title": "P", "customer_id": cid}).json()["id"]
    eid1 = client.post(
        "/employees/", json={"name": "E1", "default_hourly_rate": 600.0, "company_id": vid}
    ).json()["id"]
    eid2 = client.post(
        "/employees/", json={"name": "E2", "default_hourly_rate": 700.0, "company_id": vid}
    ).json()["id"]
    _post_expense(client, pid, eid1, category="andet", amount_excl_vat=10.0)
    _post_expense(client, pid, eid2, category="andet", amount_excl_vat=20.0)
    r = client.get(f"/expenses/?employee_id={eid1}")
    assert len(r.json()) == 1


# --- Summary ---

def test_summary(client: TestClient):
    _, pid, eid = _setup(client)
    # materialer: 1000 + 250 vat = 1250 total, billable
    _post_expense(client, pid, eid, category="materialer", amount_excl_vat=1000.0)
    # transport: 100 km * 3.76 = 376, not billable
    _post_expense(client, pid, eid, category="transport_km", km=100.0, billable=False)
    # parkering: 50, billable
    _post_expense(client, pid, eid, category="parkering", amount_excl_vat=50.0)

    r = client.get(f"/expenses/summary?project_id={pid}")
    assert r.status_code == 200
    data = r.json()
    # total: 1250 + 376 + 50 = 1676
    assert data["total_expenses"] == 1676.0
    # billable: 1250 + 50 = 1300
    assert data["billable_expenses"] == 1300.0
    # km: 100
    assert data["total_km"] == 100.0


def test_summary_unknown_project(client: TestClient):
    r = client.get("/expenses/summary?project_id=ukendt-id")
    assert r.status_code == 422


# --- Enkelt, opdater, slet ---

def test_get_expense_not_found(client: TestClient):
    assert client.get("/expenses/ukendt").status_code == 404


def test_update_expense(client: TestClient):
    _, pid, eid = _setup(client)
    expense = _post_expense(client, pid, eid, category="andet", amount_excl_vat=100.0)
    r = client.patch(
        f"/expenses/{expense['id']}", json={"description": "Ny beskrivelse", "billable": False}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["description"] == "Ny beskrivelse"
    assert data["billable"] is False
    # financial fields unchanged
    assert data["amount_total"] == 100.0


def test_deactivate_expense(client: TestClient):
    _, pid, eid = _setup(client)
    expense = _post_expense(client, pid, eid, category="andet", amount_excl_vat=100.0)
    assert client.delete(f"/expenses/{expense['id']}").status_code == 204
    assert all(e["id"] != expense["id"] for e in client.get("/expenses/").json())
    direct = client.get(f"/expenses/{expense['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False
