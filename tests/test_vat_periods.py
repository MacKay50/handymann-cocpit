from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    """Creates resources with one sent invoice and one expense (company from session)."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"title": "P", "customer_id": cid}).json()["id"]
    eid = client.post("/employees/", json={"name": "E", "default_hourly_rate": 350.0}).json()["id"]
    # Invoice: 1000 + 25% vat = 250 vat
    inv = client.post("/invoices/", json={
        "project_id": pid, "title": "Faktura",
        "issue_date": "2026-05-15", "due_date": "2026-06-15",
        "lines": [{"description": "Arbejde", "quantity": 1.0, "unit_price": 1000.0}],
    }).json()
    client.post(f"/invoices/{inv['id']}/send")
    # Expense: materialer 500 + 25% vat = 125 vat
    exp = client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "category": "materialer", "date": "2026-05-10",
        "amount_excl_vat": 500.0,
    }).json()
    return {
        "invoice_vat": inv["vat_amount"],
        "expense_vat": exp["vat_amount"],
    }


def _post_period(client: TestClient, **extra) -> dict:
    payload = {
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        **extra,
    }
    r = client.post("/vat-periods/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse ---

def test_create_vat_period(client: TestClient, company_id: str):
    data = _post_period(client)
    assert data["status"] == "open"
    assert data["active"] is True
    assert data["company_id"] == company_id
    assert data["outgoing_vat"] is None
    assert data["incoming_vat"] is None
    assert data["net_vat"] is None


def test_period_end_before_start_rejected(client: TestClient):
    r = client.post("/vat-periods/", json={
        "period_start": "2026-05-31",
        "period_end": "2026-05-01",
    })
    assert r.status_code == 422


def test_duplicate_id_rejected(client: TestClient):
    _post_period(client, **{"id": "fixed-vat"})
    r = client.post("/vat-periods/", json={
        "id": "fixed-vat",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
    })
    assert r.status_code == 409


def test_overlapping_period_rejected(client: TestClient):
    _post_period(client)
    r = client.post("/vat-periods/", json={
        "period_start": "2026-05-15",
        "period_end": "2026-06-15",
    })
    assert r.status_code == 409


def test_non_overlapping_period_allowed(client: TestClient):
    _post_period(client)
    data = _post_period(client, period_start="2026-06-01", period_end="2026-06-30")
    assert data["status"] == "open"


# --- Preview ---

def test_preview_with_data(client: TestClient):
    ctx = _setup(client)
    r = client.get("/vat-periods/preview?period_start=2026-05-01&period_end=2026-05-31")
    assert r.status_code == 200
    data = r.json()
    assert data["outgoing_vat"] == ctx["invoice_vat"]
    assert data["incoming_vat"] == ctx["expense_vat"]
    assert data["net_vat"] == ctx["invoice_vat"] - ctx["expense_vat"]
    assert data["invoice_count"] == 1
    assert data["expense_count"] == 1


def test_preview_empty(client: TestClient):
    r = client.get("/vat-periods/preview?period_start=2026-07-01&period_end=2026-07-31")
    assert r.status_code == 200
    data = r.json()
    assert data["outgoing_vat"] == 0.0
    assert data["incoming_vat"] == 0.0
    assert data["net_vat"] == 0.0
    assert data["invoice_count"] == 0
    assert data["expense_count"] == 0


# --- Lås og beregning ---

def test_lock_period(client: TestClient):
    ctx = _setup(client)
    period = _post_period(client)
    r = client.post(f"/vat-periods/{period['id']}/lock")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "locked"
    assert data["outgoing_vat"] == ctx["invoice_vat"]
    assert data["incoming_vat"] == ctx["expense_vat"]
    assert data["net_vat"] == ctx["invoice_vat"] - ctx["expense_vat"]
    assert data["invoice_count"] == 1
    assert data["expense_count"] == 1


def test_locked_amounts_frozen(client: TestClient):
    ctx = _setup(client)
    period = _post_period(client)
    client.post(f"/vat-periods/{period['id']}/lock")
    data = client.get(f"/vat-periods/{period['id']}").json()
    assert data["outgoing_vat"] == ctx["invoice_vat"]


def test_reopen_locked_period(client: TestClient):
    _setup(client)
    period = _post_period(client)
    client.post(f"/vat-periods/{period['id']}/lock")
    r = client.post(f"/vat-periods/{period['id']}/reopen")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "open"
    assert data["outgoing_vat"] is None


def test_cannot_reopen_submitted(client: TestClient):
    _setup(client)
    period = _post_period(client)
    client.post(f"/vat-periods/{period['id']}/lock")
    client.post(f"/vat-periods/{period['id']}/submit")
    r = client.post(f"/vat-periods/{period['id']}/reopen")
    assert r.status_code == 409


def test_submit_period(client: TestClient):
    _setup(client)
    period = _post_period(client)
    client.post(f"/vat-periods/{period['id']}/lock")
    r = client.post(f"/vat-periods/{period['id']}/submit")
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"


def test_submit_from_open_rejected(client: TestClient):
    period = _post_period(client)
    r = client.post(f"/vat-periods/{period['id']}/submit")
    assert r.status_code == 409


def test_lock_already_locked_rejected(client: TestClient):
    _setup(client)
    period = _post_period(client)
    client.post(f"/vat-periods/{period['id']}/lock")
    r = client.post(f"/vat-periods/{period['id']}/lock")
    assert r.status_code == 409


# --- Liste og filtrering ---

def test_list_vat_periods(client: TestClient):
    _post_period(client)
    _post_period(client, period_start="2026-06-01", period_end="2026-06-30")
    assert len(client.get("/vat-periods/").json()) == 2


def test_filter_by_status(client: TestClient):
    period = _post_period(client)
    _post_period(client, period_start="2026-06-01", period_end="2026-06-30")
    client.post(f"/vat-periods/{period['id']}/lock")
    r = client.get("/vat-periods/?status=locked")
    assert len(r.json()) == 1


def test_get_not_found(client: TestClient):
    assert client.get("/vat-periods/ukendt").status_code == 404


# --- Export ---

def test_export_locked_period(client: TestClient):
    ctx = _setup(client)
    period = _post_period(client)
    client.post(f"/vat-periods/{period['id']}/lock")
    r = client.get(f"/vat-periods/{period['id']}/export")
    assert r.status_code == 200
    data = r.json()
    assert data["outgoing_vat"] == ctx["invoice_vat"]
    assert data["incoming_vat"] == ctx["expense_vat"]
    assert data["net_vat"] == ctx["invoice_vat"] - ctx["expense_vat"]
    assert len(data["invoices"]) == 1
    assert len(data["expenses"]) == 1
    assert "invoice_number" in data["invoices"][0]


def test_export_open_period_rejected(client: TestClient):
    period = _post_period(client)
    r = client.get(f"/vat-periods/{period['id']}/export")
    assert r.status_code == 409


# --- Slet (blød) ---

def test_delete_open_period(client: TestClient):
    period = _post_period(client)
    assert client.delete(f"/vat-periods/{period['id']}").status_code == 204
    assert all(p["id"] != period["id"] for p in client.get("/vat-periods/").json())
    direct = client.get(f"/vat-periods/{period['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


def test_delete_locked_period_rejected(client: TestClient):
    _setup(client)
    period = _post_period(client)
    client.post(f"/vat-periods/{period['id']}/lock")
    r = client.delete(f"/vat-periods/{period['id']}")
    assert r.status_code == 409
