import re
from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str]:
    """Returns (project_id, customer_id); company comes from session."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"title": "Projekt", "customer_id": cid}).json()["id"]
    return pid, cid


def _post_invoice(client: TestClient, pid: str, **extra) -> dict:
    payload = {
        "project_id": pid,
        "title": "Test Faktura",
        "issue_date": "2026-05-20",
        "due_date": "2026-06-20",
        **extra,
    }
    r = client.post("/invoices/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse ---

def test_invoice_number_format(client: TestClient):
    pid, _ = _setup(client)
    data = _post_invoice(client, pid)
    assert re.match(r"^FKT-\d{4}-\d{3}$", data["invoice_number"])


def test_invoice_number_increments(client: TestClient):
    pid, _ = _setup(client)
    n1 = _post_invoice(client, pid)["invoice_number"]
    n2 = _post_invoice(client, pid)["invoice_number"]
    assert n1 != n2
    assert int(n1[-3:]) + 1 == int(n2[-3:])


def test_company_and_customer_derived(client: TestClient, company_id: str):
    pid, cid = _setup(client)
    data = _post_invoice(client, pid)
    assert data["company_id"] == company_id
    assert data["customer_id"] == cid
    assert data["status"] == "draft"
    assert data["active"] is True


def test_create_invoice_unknown_project(client: TestClient):
    r = client.post("/invoices/", json={
        "project_id": "ukendt", "title": "T",
        "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    assert r.status_code == 422


def test_create_invoice_inactive_project(client: TestClient):
    pid, _ = _setup(client)
    client.delete(f"/projects/{pid}")
    r = client.post("/invoices/", json={
        "project_id": pid, "title": "T",
        "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    assert r.status_code == 422


def test_due_date_before_issue_date(client: TestClient):
    pid, _ = _setup(client)
    r = client.post("/invoices/", json={
        "project_id": pid, "title": "T",
        "issue_date": "2026-06-20", "due_date": "2026-05-20",
    })
    assert r.status_code == 422


# --- Linjer og beregning ---

def test_create_invoice_with_lines(client: TestClient):
    pid, _ = _setup(client)
    data = _post_invoice(client, pid, lines=[
        {"description": "Maling", "unit": "m2", "quantity": 100.0, "unit_price": 80.0},
        {"description": "Afrensning", "quantity": 4.0, "unit_price": 650.0},
    ])
    lines = data["lines"]
    assert len(lines) == 2
    assert lines[0]["line_total"] == 8000.0
    assert lines[1]["line_total"] == 2600.0
    assert data["subtotal"] == 10600.0
    assert data["vat_amount"] == 2650.0
    assert data["total"] == 13250.0


def test_vat_always_server_calculated(client: TestClient):
    pid, _ = _setup(client)
    data = _post_invoice(client, pid, lines=[
        {"description": "Test", "quantity": 1.0, "unit_price": 1000.0},
    ])
    assert data["vat_amount"] == 250.0
    assert data["total"] == 1250.0


def test_empty_invoice_totals(client: TestClient):
    pid, _ = _setup(client)
    data = _post_invoice(client, pid)
    assert data["subtotal"] == 0.0
    assert data["vat_amount"] == 0.0
    assert data["total"] == 0.0


def test_line_total_precision(client: TestClient):
    pid, _ = _setup(client)
    data = _post_invoice(client, pid, lines=[
        {"description": "Test", "quantity": 3.0, "unit_price": 333.33},
    ])
    assert data["lines"][0]["line_total"] == 999.99


# --- Liste og filtrering ---

def test_list_invoices(client: TestClient):
    pid, _ = _setup(client)
    _post_invoice(client, pid)
    _post_invoice(client, pid)
    assert len(client.get("/invoices/").json()) == 2


def test_filter_by_project(client: TestClient):
    pid1, _ = _setup(client)
    pid2, _ = _setup(client)
    _post_invoice(client, pid1)
    _post_invoice(client, pid2)
    r = client.get(f"/invoices/?project_id={pid1}")
    assert len(r.json()) == 1


def test_filter_by_company_returns_session_only(client: TestClient):
    pid, _ = _setup(client)
    _post_invoice(client, pid)
    # List returns only session company's invoices
    r = client.get("/invoices/")
    assert len(r.json()) == 1


def test_filter_by_status(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    _post_invoice(client, pid)
    client.post(f"/invoices/{inv['id']}/send")
    r = client.get("/invoices/?status=sent")
    assert len(r.json()) == 1


# --- Summary ---

def test_summary(client: TestClient):
    pid, _ = _setup(client)
    inv1 = _post_invoice(client, pid, lines=[
        {"description": "A", "quantity": 1.0, "unit_price": 1000.0},
    ])
    inv2 = _post_invoice(client, pid, lines=[
        {"description": "B", "quantity": 1.0, "unit_price": 500.0},
    ])
    client.post(f"/invoices/{inv1['id']}/send")
    client.post(f"/invoices/{inv2['id']}/send")
    client.post(f"/invoices/{inv1['id']}/pay")

    r = client.get(f"/invoices/summary?project_id={pid}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_invoiced"] == 1875.0
    assert data["total_paid"] == 1250.0
    assert data["outstanding"] == 625.0


def test_summary_unknown_project(client: TestClient):
    r = client.get("/invoices/summary?project_id=ukendt")
    assert r.status_code == 422


# --- Enkelt, opdater, slet ---

def test_get_invoice_not_found(client: TestClient):
    assert client.get("/invoices/ukendt").status_code == 404


def test_update_draft_invoice(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid, lines=[
        {"description": "A", "quantity": 1.0, "unit_price": 500.0},
    ])
    r = client.patch(f"/invoices/{inv['id']}", json={
        "title": "Opdateret",
        "lines": [{"description": "B", "quantity": 2.0, "unit_price": 300.0}],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Opdateret"
    assert data["lines"][0]["line_total"] == 600.0
    assert data["subtotal"] == 600.0
    assert data["total"] == 750.0


def test_update_sent_invoice_rejected(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    client.post(f"/invoices/{inv['id']}/send")
    r = client.patch(f"/invoices/{inv['id']}", json={"title": "Nyt"})
    assert r.status_code == 409


# --- Status-overgange ---

def test_send_invoice(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    r = client.post(f"/invoices/{inv['id']}/send")
    assert r.status_code == 200
    assert r.json()["status"] == "sent"


def test_pay_invoice(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    client.post(f"/invoices/{inv['id']}/send")
    r = client.post(f"/invoices/{inv['id']}/pay")
    assert r.status_code == 200
    assert r.json()["status"] == "paid"


def test_cancel_from_draft(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    r = client.post(f"/invoices/{inv['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_cancel_from_sent(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    client.post(f"/invoices/{inv['id']}/send")
    r = client.post(f"/invoices/{inv['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_invalid_transition_pay_from_draft(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    r = client.post(f"/invoices/{inv['id']}/pay")
    assert r.status_code == 409


def test_invalid_transition_from_paid(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    client.post(f"/invoices/{inv['id']}/send")
    client.post(f"/invoices/{inv['id']}/pay")
    r = client.post(f"/invoices/{inv['id']}/cancel")
    assert r.status_code == 409


def test_duplicate_id_rejected(client: TestClient):
    pid, _ = _setup(client)
    _post_invoice(client, pid, **{"id": "fixed-id"})
    r = client.post("/invoices/", json={
        "id": "fixed-id", "project_id": pid, "title": "Duplikat",
        "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    assert r.status_code == 409


def test_summary_excludes_cancelled(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid, lines=[
        {"description": "A", "quantity": 1.0, "unit_price": 1000.0},
    ])
    client.post(f"/invoices/{inv['id']}/cancel")
    r = client.get(f"/invoices/summary?project_id={pid}")
    assert r.json()["total_invoiced"] == 0.0


def test_deactivate_invoice(client: TestClient):
    pid, _ = _setup(client)
    inv = _post_invoice(client, pid)
    assert client.delete(f"/invoices/{inv['id']}").status_code == 204
    assert all(i["id"] != inv["id"] for i in client.get("/invoices/").json())
    direct = client.get(f"/invoices/{inv['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


# --- Draft from project ---

def _add_time_entry(client: TestClient, pid: str, eid: str, hours: float = 4.0) -> dict:
    r = client.post("/time-entries/", json={
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": hours, "description": "Maling",
    })
    assert r.status_code == 201, r.json()
    return r.json()


def _add_expense(client: TestClient, pid: str, eid: str, amount: float = 200.0) -> dict:
    r = client.post("/expenses/", json={
        "project_id": pid, "employee_id": eid,
        "category": "materialer", "date": "2026-05-20",
        "description": "Maling hvid", "amount_excl_vat": amount,
    })
    assert r.status_code == 201, r.json()
    return r.json()


def _setup_with_employee(client: TestClient) -> tuple[str, str, str]:
    """Returns (project_id, customer_id, employee_id); company from session."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"title": "Malerwork", "customer_id": cid}).json()["id"]
    eid = client.post("/employees/", json={"name": "Lars", "default_hourly_rate": 500.0}).json()["id"]
    return pid, cid, eid


def test_draft_from_project_creates_invoice(client: TestClient):
    pid, _, eid = _setup_with_employee(client)
    _add_time_entry(client, pid, eid, hours=2.0)
    r = client.post("/invoices/draft-from-project", json={
        "project_id": pid, "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["status"] == "draft"
    assert data["project_id"] == pid
    assert len(data["lines"]) == 1
    assert data["lines"][0]["quantity"] == 2.0
    assert data["lines"][0]["unit"] == "timer"


def test_draft_from_project_with_expenses(client: TestClient):
    pid, _, eid = _setup_with_employee(client)
    _add_time_entry(client, pid, eid, hours=3.0)
    _add_expense(client, pid, eid, amount=150.0)
    r = client.post("/invoices/draft-from-project", json={
        "project_id": pid, "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    assert r.status_code == 201, r.json()
    data = r.json()
    assert len(data["lines"]) == 2


def test_draft_from_project_marks_entries_billed(client: TestClient):
    pid, _, eid = _setup_with_employee(client)
    entry = _add_time_entry(client, pid, eid)
    client.post("/invoices/draft-from-project", json={
        "project_id": pid, "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    entry_data = client.get(f"/time-entries/{entry['id']}").json()
    assert entry_data["invoice_id"] is not None


def test_draft_from_project_marks_expenses_billed(client: TestClient):
    pid, _, eid = _setup_with_employee(client)
    expense = _add_expense(client, pid, eid)
    client.post("/invoices/draft-from-project", json={
        "project_id": pid, "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    expense_data = client.get(f"/expenses/{expense['id']}").json()
    assert expense_data["invoice_id"] is not None


def test_draft_from_project_no_unbilled_rejected(client: TestClient):
    pid, _, _ = _setup_with_employee(client)
    r = client.post("/invoices/draft-from-project", json={
        "project_id": pid, "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    assert r.status_code == 422


def test_draft_from_project_skips_already_billed(client: TestClient):
    pid, _, eid = _setup_with_employee(client)
    _add_time_entry(client, pid, eid, hours=2.0)
    client.post("/invoices/draft-from-project", json={
        "project_id": pid, "issue_date": "2026-05-20", "due_date": "2026-06-20",
    })
    _add_time_entry(client, pid, eid, hours=1.0)
    r = client.post("/invoices/draft-from-project", json={
        "project_id": pid, "issue_date": "2026-05-21", "due_date": "2026-06-21",
    })
    assert r.status_code == 201
    assert len(r.json()["lines"]) == 1


def test_draft_from_project_custom_title(client: TestClient):
    pid, _, eid = _setup_with_employee(client)
    _add_time_entry(client, pid, eid)
    r = client.post("/invoices/draft-from-project", json={
        "project_id": pid, "issue_date": "2026-05-20", "due_date": "2026-06-20",
        "title": "Slutopgørelse",
    })
    assert r.status_code == 201
    assert r.json()["title"] == "Slutopgørelse"
