"""CSV export for all five report endpoints."""
from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str, str, str]:
    """Returns (company_id, project_id, customer_id, employee_id)."""
    vid = client.post("/companies/", json={"name": "CSV Firma"}).json()["id"]
    cid = client.post("/customers/", json={"name": "CSV Kunde", "company_id": vid}).json()["id"]
    eid = client.post("/employees/", json={
        "name": "CSV Medarbejder", "default_hourly_rate": 400.0, "company_id": vid,
    }).json()["id"]
    pid = client.post("/projects/", json={"title": "CSV Projekt", "customer_id": cid}).json()["id"]
    return vid, pid, cid, eid


def _invoice(client, pid, issue_date, amount, status="sent"):
    inv = client.post("/invoices/", json={
        "project_id": pid, "title": "F",
        "issue_date": issue_date, "due_date": "2099-12-31",
        "lines": [{"description": "Arbejde", "quantity": 1.0, "unit_price": amount}],
    }).json()
    if status in ("sent", "paid"):
        client.post(f"/invoices/{inv['id']}/send")
    if status == "paid":
        client.post(f"/invoices/{inv['id']}/pay")
    return inv


# ── Revenue CSV ───────────────────────────────────────────────────────────────

def test_revenue_csv_status_ok(client: TestClient):
    vid, pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-03-01", 1000.0)
    r = client.get(f"/reports/revenue?company_id={vid}&year=2026&format=csv")
    assert r.status_code == 200


def test_revenue_csv_content_type(client: TestClient):
    vid, pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-03-01", 1000.0)
    r = client.get(f"/reports/revenue?company_id={vid}&year=2026&format=csv")
    assert "text/csv" in r.headers["content-type"]


def test_revenue_csv_content_disposition(client: TestClient):
    vid, pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-03-01", 1000.0)
    r = client.get(f"/reports/revenue?company_id={vid}&year=2026&format=csv")
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".csv" in cd


def test_revenue_csv_header_row(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/revenue?company_id={vid}&year=2026&format=csv")
    first_line = r.text.splitlines()[0]
    assert first_line == "period,invoice_count,invoiced_amount,paid_amount,outstanding_amount"


def test_revenue_csv_data_rows(client: TestClient):
    vid, pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-01-01", 1000.0)
    _invoice(client, pid, "2026-03-01", 2000.0)
    r = client.get(f"/reports/revenue?company_id={vid}&year=2026&group_by=month&format=csv")
    lines = r.text.splitlines()
    assert len(lines) == 3  # header + 2 months


def test_revenue_csv_empty_returns_header_only(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/revenue?company_id={vid}&year=2026&format=csv")
    lines = r.text.splitlines()
    assert len(lines) == 1


# ── Project profitability CSV ─────────────────────────────────────────────────

def test_profitability_csv_status_ok(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/project-profitability?company_id={vid}&format=csv")
    assert r.status_code == 200


def test_profitability_csv_content_type(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/project-profitability?company_id={vid}&format=csv")
    assert "text/csv" in r.headers["content-type"]


def test_profitability_csv_header_row(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/project-profitability?company_id={vid}&format=csv")
    first_line = r.text.splitlines()[0]
    assert first_line == "project_id,project_title,customer_name,invoiced_total,hours_cost,expenses_cost,gross_margin"


def test_profitability_csv_data_rows(client: TestClient):
    vid, pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-05-01", 1000.0)
    r = client.get(f"/reports/project-profitability?company_id={vid}&format=csv")
    lines = r.text.splitlines()
    assert len(lines) == 2  # header + 1 project


# ── Employee hours CSV ────────────────────────────────────────────────────────

def test_employee_hours_csv_status_ok(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/employee-hours?company_id={vid}&from_date=2026-01-01&to_date=2026-12-31&format=csv")
    assert r.status_code == 200


def test_employee_hours_csv_content_type(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/employee-hours?company_id={vid}&from_date=2026-01-01&to_date=2026-12-31&format=csv")
    assert "text/csv" in r.headers["content-type"]


def test_employee_hours_csv_header_row(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/employee-hours?company_id={vid}&from_date=2026-01-01&to_date=2026-12-31&format=csv")
    first_line = r.text.splitlines()[0]
    assert first_line == "employee_id,employee_name,total_hours,billable_hours,total_cost,billable_cost"


def test_employee_hours_csv_data_rows(client: TestClient):
    vid, pid, _, eid = _setup(client)
    client.post("/time-entries/", json={
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": 6.0, "billable": True,
    })
    r = client.get(f"/reports/employee-hours?company_id={vid}&from_date=2026-01-01&to_date=2026-12-31&format=csv")
    lines = r.text.splitlines()
    assert len(lines) == 2  # header + 1 employee


def test_employee_hours_csv_empty_returns_header_only(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/employee-hours?company_id={vid}&from_date=2026-01-01&to_date=2026-12-31&format=csv")
    lines = r.text.splitlines()
    assert len(lines) == 1


# ── Top customers CSV ─────────────────────────────────────────────────────────

def test_top_customers_csv_status_ok(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/top-customers?company_id={vid}&year=2026&format=csv")
    assert r.status_code == 200


def test_top_customers_csv_content_type(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/top-customers?company_id={vid}&year=2026&format=csv")
    assert "text/csv" in r.headers["content-type"]


def test_top_customers_csv_header_row(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/top-customers?company_id={vid}&year=2026&format=csv")
    first_line = r.text.splitlines()[0]
    assert first_line == "customer_id,customer_name,project_count,invoiced_total,paid_total"


def test_top_customers_csv_data_rows(client: TestClient):
    vid, pid, _, _ = _setup(client)
    _invoice(client, pid, "2026-05-01", 500.0)
    r = client.get(f"/reports/top-customers?company_id={vid}&year=2026&format=csv")
    lines = r.text.splitlines()
    assert len(lines) == 2  # header + 1 customer


# ── Expense breakdown CSV ─────────────────────────────────────────────────────

def test_expense_breakdown_csv_status_ok(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/expense-breakdown?company_id={vid}&year=2026&format=csv")
    assert r.status_code == 200


def test_expense_breakdown_csv_content_type(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/expense-breakdown?company_id={vid}&year=2026&format=csv")
    assert "text/csv" in r.headers["content-type"]


def test_expense_breakdown_csv_header_row(client: TestClient):
    vid, _, _, _ = _setup(client)
    r = client.get(f"/reports/expense-breakdown?company_id={vid}&year=2026&format=csv")
    first_line = r.text.splitlines()[0]
    assert first_line == "category,expense_count,total_excl_vat,total_vat,total_amount"


def test_expense_breakdown_csv_data_rows(client: TestClient):
    vid, pid, _, eid = _setup(client)
    client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "category": "materialer", "date": "2026-05-20",
        "description": "Test", "amount_excl_vat": 200.0,
    })
    r = client.get(f"/reports/expense-breakdown?company_id={vid}&year=2026&format=csv")
    lines = r.text.splitlines()
    assert len(lines) == 2  # header + 1 category
