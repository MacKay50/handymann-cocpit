from fastapi.testclient import TestClient


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _setup(client: TestClient) -> tuple[str, str, str]:
    """Returns (project_id, customer_id, employee_id); company comes from session."""
    cid = client.post("/customers/", json={"name": "Familie Hansen"}).json()["id"]
    eid = client.post("/employees/", json={
        "name": "Lars Maler", "default_hourly_rate": 500.0,
    }).json()["id"]
    pid = client.post("/projects/", json={"title": "Stue + køkken", "customer_id": cid}).json()["id"]
    return pid, cid, eid


def _invoice(client, pid, issue_date, total_excl_vat, status="sent"):
    inv = client.post("/invoices/", json={
        "project_id": pid, "title": "F",
        "issue_date": issue_date, "due_date": "2099-12-31",
        "lines": [{"description": "Arbejde", "quantity": 1.0, "unit_price": total_excl_vat}],
    }).json()
    if status in ("sent", "paid"):
        client.post(f"/invoices/{inv['id']}/send")
    if status == "paid":
        client.post(f"/invoices/{inv['id']}/pay")
    return inv


def _time_entry(client, pid, eid, hours, date="2026-05-20", billable=True):
    return client.post("/time-entries/", json={
        "project_id": pid, "employee_id": eid,
        "date": date, "hours": hours, "billable": billable,
    }).json()


def _expense(client, pid, eid, amount, category="materialer", billable=True):
    return client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "category": category, "date": "2026-05-20",
        "description": "Test", "amount_excl_vat": amount, "billable": billable,
    }).json()


# ─── Revenue ──────────────────────────────────────────────────────────────────

def test_revenue_monthly_groups(client: TestClient):
    pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-01-15", 1000.0)
    _invoice(client, pid, "2026-01-20", 2000.0)
    _invoice(client, pid, "2026-03-10", 500.0)
    r = client.get("/reports/revenue?year=2026&group_by=month")
    assert r.status_code == 200
    rows = {row["period"]: row for row in r.json()}
    assert "2026-01" in rows
    assert "2026-03" in rows
    assert rows["2026-01"]["invoice_count"] == 2


def test_revenue_monthly_amounts(client: TestClient):
    pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-05-10", 1000.0, status="sent")
    r = client.get("/reports/revenue?year=2026&group_by=month")
    rows = {row["period"]: row for row in r.json()}
    assert rows["2026-05"]["invoiced_amount"] == 1250.0
    assert rows["2026-05"]["paid_amount"] == 0.0
    assert rows["2026-05"]["outstanding_amount"] == 1250.0


def test_revenue_paid_amount(client: TestClient):
    pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-05-10", 800.0, status="paid")
    r = client.get("/reports/revenue?year=2026&group_by=month")
    rows = {row["period"]: row for row in r.json()}
    assert rows["2026-05"]["paid_amount"] == 1000.0
    assert rows["2026-05"]["outstanding_amount"] == 0.0


def test_revenue_excludes_cancelled(client: TestClient):
    pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-05-10", 1000.0, status="draft")
    inv_c = _invoice(client, pid, "2026-05-11", 500.0, status="sent")
    client.post(f"/invoices/{inv_c['id']}/cancel")
    r = client.get("/reports/revenue?year=2026&group_by=month")
    assert r.json() == []


def test_revenue_quarterly_groups(client: TestClient):
    pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-02-01", 1000.0)
    _invoice(client, pid, "2026-05-01", 2000.0)
    r = client.get("/reports/revenue?year=2026&group_by=quarter")
    rows = {row["period"]: row for row in r.json()}
    assert "2026-Q1" in rows
    assert "2026-Q2" in rows


def test_revenue_yearly_single_row(client: TestClient):
    pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-01-01", 1000.0)
    _invoice(client, pid, "2026-06-01", 2000.0)
    r = client.get("/reports/revenue?year=2026&group_by=year")
    assert len(r.json()) == 1
    assert r.json()[0]["period"] == "2026"
    assert r.json()[0]["invoice_count"] == 2


def test_revenue_only_matches_year(client: TestClient):
    pid, _, _ = _setup(client)
    _invoice(client, pid, "2025-12-01", 1000.0)
    _invoice(client, pid, "2026-01-01", 500.0)
    r = client.get("/reports/revenue?year=2026&group_by=year")
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["invoiced_amount"] == 625.0  # 500 + 25% moms


# ─── Project profitability ────────────────────────────────────────────────────

def test_profitability_basic(client: TestClient):
    pid, cid, eid = _setup(client)
    _invoice(client, pid, "2026-05-20", 4000.0, status="sent")
    _time_entry(client, pid, eid, 4.0)
    _expense(client, pid, eid, 500.0)
    r = client.get("/reports/project-profitability")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["project_id"] == pid
    assert row["project_title"] == "Stue + køkken"
    assert row["invoiced_total"] == 5000.0
    assert row["hours_cost"] == 2000.0
    assert row["expenses_cost"] == 625.0
    assert row["gross_margin"] == 5000.0 - 2000.0 - 625.0


def test_profitability_excludes_cancelled_invoices(client: TestClient):
    pid, _, eid = _setup(client)
    inv = _invoice(client, pid, "2026-05-20", 1000.0, status="sent")
    client.post(f"/invoices/{inv['id']}/cancel")
    r = client.get("/reports/project-profitability")
    assert r.json()[0]["invoiced_total"] == 0.0


def test_profitability_excludes_inactive_projects(client: TestClient):
    pid, _, _ = _setup(client)
    client.delete(f"/projects/{pid}")
    r = client.get("/reports/project-profitability")
    assert r.json() == []


def test_profitability_customer_name(client: TestClient):
    _setup(client)
    r = client.get("/reports/project-profitability")
    assert r.json()[0]["customer_name"] == "Familie Hansen"


# ─── Employee hours ───────────────────────────────────────────────────────────

def test_employee_hours_sums(client: TestClient):
    pid, _, eid = _setup(client)
    _time_entry(client, pid, eid, 3.0, date="2026-05-10")
    _time_entry(client, pid, eid, 5.0, date="2026-05-15")
    r = client.get("/reports/employee-hours?from_date=2026-01-01&to_date=2026-12-31")
    assert r.status_code == 200
    assert len(r.json()) == 1
    row = r.json()[0]
    assert row["employee_name"] == "Lars Maler"
    assert row["total_hours"] == 8.0
    assert row["total_cost"] == 4000.0


def test_employee_hours_billable_split(client: TestClient):
    pid, _, eid = _setup(client)
    _time_entry(client, pid, eid, 4.0, billable=True)
    _time_entry(client, pid, eid, 2.0, billable=False)
    r = client.get("/reports/employee-hours?from_date=2026-01-01&to_date=2026-12-31")
    row = r.json()[0]
    assert row["total_hours"] == 6.0
    assert row["billable_hours"] == 4.0
    assert row["billable_cost"] == 2000.0


def test_employee_hours_date_filter(client: TestClient):
    pid, _, eid = _setup(client)
    _time_entry(client, pid, eid, 8.0, date="2026-01-10")
    _time_entry(client, pid, eid, 4.0, date="2026-06-10")
    r = client.get("/reports/employee-hours?from_date=2026-06-01&to_date=2026-12-31")
    assert r.json()[0]["total_hours"] == 4.0


def test_employee_hours_excludes_inactive(client: TestClient):
    pid, _, eid = _setup(client)
    entry = _time_entry(client, pid, eid, 8.0)
    client.delete(f"/time-entries/{entry['id']}")
    r = client.get("/reports/employee-hours?from_date=2026-01-01&to_date=2026-12-31")
    assert r.json() == []


# ─── Top customers ────────────────────────────────────────────────────────────

def test_top_customers_sorted_by_revenue(client: TestClient):
    c1 = client.post("/customers/", json={"name": "Stor Kunde"}).json()["id"]
    c2 = client.post("/customers/", json={"name": "Lille Kunde"}).json()["id"]
    p1 = client.post("/projects/", json={"title": "Stor sag", "customer_id": c1}).json()["id"]
    p2 = client.post("/projects/", json={"title": "Lille sag", "customer_id": c2}).json()["id"]
    _invoice(client, p1, "2026-05-01", 5000.0, status="paid")
    _invoice(client, p2, "2026-05-01", 1000.0, status="sent")
    r = client.get("/reports/top-customers?year=2026")
    rows = r.json()
    assert rows[0]["customer_name"] == "Stor Kunde"
    assert rows[1]["customer_name"] == "Lille Kunde"


def test_top_customers_invoiced_and_paid(client: TestClient):
    pid, cid, _ = _setup(client)
    _invoice(client, pid, "2026-05-01", 2000.0, status="paid")
    _invoice(client, pid, "2026-05-15", 1000.0, status="sent")
    r = client.get("/reports/top-customers?year=2026")
    row = r.json()[0]
    assert row["customer_id"] == cid
    assert row["invoiced_total"] == 3750.0
    assert row["paid_total"] == 2500.0


def test_top_customers_limit(client: TestClient):
    for i in range(5):
        cid = client.post("/customers/", json={"name": f"Kunde {i}"}).json()["id"]
        pid = client.post("/projects/", json={"title": f"Sag {i}", "customer_id": cid}).json()["id"]
        _invoice(client, pid, "2026-05-01", float(1000 + i * 100), status="sent")
    r = client.get("/reports/top-customers?year=2026&limit=3")
    assert len(r.json()) == 3


def test_top_customers_project_count(client: TestClient):
    pid, cid, _ = _setup(client)
    pid2 = client.post("/projects/", json={"title": "Sag 2", "customer_id": cid}).json()["id"]
    _invoice(client, pid2, "2026-05-01", 500.0, status="sent")
    r = client.get("/reports/top-customers?year=2026")
    assert r.json()[0]["project_count"] >= 1


# ─── Expense breakdown ────────────────────────────────────────────────────────

def test_expense_breakdown_by_category(client: TestClient):
    pid, _, eid = _setup(client)
    _expense(client, pid, eid, 300.0, category="materialer")
    _expense(client, pid, eid, 200.0, category="materialer")
    _expense(client, pid, eid, 50.0,  category="parkering")
    r = client.get("/reports/expense-breakdown?year=2026")
    assert r.status_code == 200
    rows = {row["category"]: row for row in r.json()}
    assert "materialer" in rows
    assert "parkering" in rows
    assert rows["materialer"]["expense_count"] == 2
    assert rows["materialer"]["total_excl_vat"] == 500.0


def test_expense_breakdown_vat_amounts(client: TestClient):
    pid, _, eid = _setup(client)
    _expense(client, pid, eid, 400.0, category="materialer")
    r = client.get("/reports/expense-breakdown?year=2026")
    row = [x for x in r.json() if x["category"] == "materialer"][0]
    assert row["total_vat"] == 100.0
    assert row["total_amount"] == 500.0


def test_expense_breakdown_date_filter(client: TestClient):
    pid, _, eid = _setup(client)
    client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "category": "materialer", "date": "2025-12-01",
        "description": "Gammelt udlæg", "amount_excl_vat": 1000.0,
    })
    _expense(client, pid, eid, 200.0, category="materialer")
    r = client.get("/reports/expense-breakdown?year=2026")
    rows = {row["category"]: row for row in r.json()}
    assert rows["materialer"]["total_excl_vat"] == 200.0


def test_expense_breakdown_excludes_inactive(client: TestClient):
    pid, _, eid = _setup(client)
    exp = _expense(client, pid, eid, 300.0)
    client.delete(f"/expenses/{exp['id']}")
    r = client.get("/reports/expense-breakdown?year=2026")
    assert r.json() == []
