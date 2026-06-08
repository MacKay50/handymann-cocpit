from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    """Returns dict with employee_id; company comes from session."""
    eid = client.post("/employees/", json={
        "name": "Maler", "default_hourly_rate": 350.0,
    }).json()["id"]
    return {"employee_id": eid}


def _post_salary(client: TestClient, employee_id: str, **extra) -> dict:
    payload = {
        "employee_id": employee_id,
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "gross_amount": 40000.0,
        "tax_percentage": 38.0,
        **extra,
    }
    r = client.post("/salaries/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse og beregning ---

def test_create_salary(client: TestClient, company_id: str):
    ctx = _setup(client)
    data = _post_salary(client, ctx["employee_id"])
    assert data["status"] == "draft"
    assert data["active"] is True
    assert data["company_id"] == company_id
    assert data["employee_id"] == ctx["employee_id"]


def test_tax_and_net_calculated(client: TestClient):
    ctx = _setup(client)
    data = _post_salary(client, ctx["employee_id"], gross_amount=40000.0, tax_percentage=38.0)
    assert data["tax_amount"] == 15200.0
    assert data["net_amount"] == 24800.0


def test_zero_tax_allowed(client: TestClient):
    ctx = _setup(client)
    data = _post_salary(client, ctx["employee_id"], gross_amount=10000.0, tax_percentage=0.0)
    assert data["tax_amount"] == 0.0
    assert data["net_amount"] == 10000.0


def test_tax_rounding(client: TestClient):
    ctx = _setup(client)
    data = _post_salary(client, ctx["employee_id"], gross_amount=10000.0, tax_percentage=38.5)
    assert data["tax_amount"] == 3850.0
    assert data["net_amount"] == 6150.0


def test_period_end_before_start_rejected(client: TestClient):
    ctx = _setup(client)
    r = client.post("/salaries/", json={
        "employee_id": ctx["employee_id"],
        "period_start": "2026-05-31",
        "period_end": "2026-05-01",
        "gross_amount": 40000.0,
        "tax_percentage": 38.0,
    })
    assert r.status_code == 422


def test_negative_gross_rejected(client: TestClient):
    ctx = _setup(client)
    r = client.post("/salaries/", json={
        "employee_id": ctx["employee_id"],
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "gross_amount": -1000.0,
        "tax_percentage": 38.0,
    })
    assert r.status_code == 422


def test_tax_over_100_rejected(client: TestClient):
    ctx = _setup(client)
    r = client.post("/salaries/", json={
        "employee_id": ctx["employee_id"],
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "gross_amount": 40000.0,
        "tax_percentage": 101.0,
    })
    assert r.status_code == 422


def test_unknown_employee_rejected(client: TestClient):
    r = client.post("/salaries/", json={
        "employee_id": "ukendt",
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "gross_amount": 40000.0,
        "tax_percentage": 38.0,
    })
    assert r.status_code == 422


def test_inactive_employee_rejected(client: TestClient):
    ctx = _setup(client)
    client.delete(f"/employees/{ctx['employee_id']}")
    r = client.post("/salaries/", json={
        "employee_id": ctx["employee_id"],
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "gross_amount": 40000.0,
        "tax_percentage": 38.0,
    })
    assert r.status_code == 422


def test_duplicate_id_rejected(client: TestClient):
    ctx = _setup(client)
    _post_salary(client, ctx["employee_id"], **{"id": "fixed-sal"})
    r = client.post("/salaries/", json={
        "id": "fixed-sal",
        "employee_id": ctx["employee_id"],
        "period_start": "2026-05-01",
        "period_end": "2026-05-31",
        "gross_amount": 40000.0,
        "tax_percentage": 38.0,
    })
    assert r.status_code == 409


# --- Opdatering ---

def test_update_draft_salary(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    r = client.patch(f"/salaries/{sal['id']}", json={
        "gross_amount": 45000.0,
        "tax_percentage": 40.0,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["gross_amount"] == 45000.0
    assert data["tax_amount"] == 18000.0
    assert data["net_amount"] == 27000.0


def test_update_period_dates(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    r = client.patch(f"/salaries/{sal['id']}", json={
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
    })
    assert r.status_code == 200
    assert r.json()["period_start"] == "2026-06-01"


def test_update_period_end_before_start_rejected(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    r = client.patch(f"/salaries/{sal['id']}", json={"period_end": "2026-04-01"})
    assert r.status_code == 422


def test_update_approved_salary_rejected(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    client.post(f"/salaries/{sal['id']}/approve")
    r = client.patch(f"/salaries/{sal['id']}", json={"gross_amount": 99000.0})
    assert r.status_code == 409


def test_get_salary_not_found(client: TestClient):
    assert client.get("/salaries/ukendt").status_code == 404


# --- Liste og filtrering ---

def test_list_salaries(client: TestClient):
    ctx = _setup(client)
    _post_salary(client, ctx["employee_id"])
    _post_salary(client, ctx["employee_id"], period_start="2026-06-01", period_end="2026-06-30")
    assert len(client.get("/salaries/").json()) == 2


def test_filter_by_session_company_only(client: TestClient):
    ctx = _setup(client)
    _post_salary(client, ctx["employee_id"])
    r = client.get("/salaries/")
    assert len(r.json()) == 1


def test_filter_by_employee_id(client: TestClient):
    eid1 = client.post("/employees/", json={"name": "E1", "default_hourly_rate": 300.0}).json()["id"]
    eid2 = client.post("/employees/", json={"name": "E2", "default_hourly_rate": 300.0}).json()["id"]
    _post_salary(client, eid1)
    _post_salary(client, eid2)
    r = client.get(f"/salaries/?employee_id={eid1}")
    assert len(r.json()) == 1


def test_filter_by_status(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    _post_salary(client, ctx["employee_id"], period_start="2026-06-01", period_end="2026-06-30")
    client.post(f"/salaries/{sal['id']}/approve")
    r = client.get("/salaries/?status=approved")
    assert len(r.json()) == 1


def test_filter_by_period_from(client: TestClient):
    ctx = _setup(client)
    _post_salary(client, ctx["employee_id"], period_start="2026-03-01", period_end="2026-03-31")
    _post_salary(client, ctx["employee_id"], period_start="2026-06-01", period_end="2026-06-30")
    r = client.get("/salaries/?period_from=2026-05-01")
    assert len(r.json()) == 1
    assert r.json()[0]["period_start"] == "2026-06-01"


def test_filter_by_period_to(client: TestClient):
    ctx = _setup(client)
    _post_salary(client, ctx["employee_id"], period_start="2026-03-01", period_end="2026-03-31")
    _post_salary(client, ctx["employee_id"], period_start="2026-06-01", period_end="2026-06-30")
    r = client.get("/salaries/?period_to=2026-04-30")
    assert len(r.json()) == 1
    assert r.json()[0]["period_start"] == "2026-03-01"


def test_list_excludes_inactive(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    client.delete(f"/salaries/{sal['id']}")
    assert len(client.get("/salaries/").json()) == 0


# --- Status-overgange ---

def test_approve_salary(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    r = client.post(f"/salaries/{sal['id']}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_pay_salary(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    client.post(f"/salaries/{sal['id']}/approve")
    r = client.post(f"/salaries/{sal['id']}/pay")
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


def test_cancel_draft_salary(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    r = client.post(f"/salaries/{sal['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_invalid_pay_from_draft(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    r = client.post(f"/salaries/{sal['id']}/pay")
    assert r.status_code == 409


def test_invalid_cancel_approved(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    client.post(f"/salaries/{sal['id']}/approve")
    r = client.post(f"/salaries/{sal['id']}/cancel")
    assert r.status_code == 409


def test_invalid_transition_from_paid(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    client.post(f"/salaries/{sal['id']}/approve")
    client.post(f"/salaries/{sal['id']}/pay")
    r = client.post(f"/salaries/{sal['id']}/cancel")
    assert r.status_code == 409


# --- Summary ---

def test_summary_no_salaries(client: TestClient):
    ctx = _setup(client)
    r = client.get(f"/salaries/summary?employee_id={ctx['employee_id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_gross"] == 0.0
    assert data["count"] == 0


def test_summary_multiple_salaries(client: TestClient):
    ctx = _setup(client)
    _post_salary(client, ctx["employee_id"])
    _post_salary(client, ctx["employee_id"],
                 period_start="2026-06-01", period_end="2026-06-30",
                 gross_amount=42000.0)
    r = client.get(f"/salaries/summary?employee_id={ctx['employee_id']}")
    data = r.json()
    assert data["total_gross"] == 82000.0
    assert data["count"] == 2


def test_summary_excludes_cancelled(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    client.post(f"/salaries/{sal['id']}/cancel")
    r = client.get(f"/salaries/summary?employee_id={ctx['employee_id']}")
    assert r.json()["total_gross"] == 0.0
    assert r.json()["count"] == 0


def test_summary_by_session_company(client: TestClient):
    ctx = _setup(client)
    _post_salary(client, ctx["employee_id"])
    # Summary always scoped to session company
    r = client.get("/salaries/summary")
    assert r.json()["total_gross"] == 40000.0


def test_summary_unknown_employee(client: TestClient):
    r = client.get("/salaries/summary?employee_id=ukendt")
    assert r.status_code == 422


# --- Slet (blød) ---

def test_deactivate_salary(client: TestClient):
    ctx = _setup(client)
    sal = _post_salary(client, ctx["employee_id"])
    assert client.delete(f"/salaries/{sal['id']}").status_code == 204
    assert all(s["id"] != sal["id"] for s in client.get("/salaries/").json())
    direct = client.get(f"/salaries/{sal['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False
