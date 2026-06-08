import pathlib
from datetime import date, timedelta
from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str]:
    """Returns (customer_id, employee_id); company comes from session."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    eid = client.post("/employees/", json={"name": "Lars", "default_hourly_rate": 500.0}).json()["id"]
    return cid, eid


def _today() -> str:
    return date.today().isoformat()


def _days(n: int) -> str:
    return (date.today() + timedelta(days=n)).isoformat()


def _get_dashboard(client: TestClient) -> dict:
    r = client.get("/dashboard")
    assert r.status_code == 200, r.json()
    return r.json()


# --- Grundstruktur ---

def test_dashboard_has_expected_fields(client: TestClient):
    data = _get_dashboard(client)
    for field in [
        "company_id", "inbox_unread", "enquiries_new", "enquiries_qualified",
        "projects_draft", "projects_active", "quotes_awaiting",
        "invoices_draft", "invoices_outstanding", "invoices_overdue_count",
        "invoices_overdue_amount", "reminders_pending",
        "deadlines_overdue", "deadlines_upcoming",
        "reconciliation_unmatched_invoices",
        "reconciliation_overdue_invoices",
        "reconciliation_overdue_amount_ore",
    ]:
        assert field in data, f"Missing field: {field}"


def test_dashboard_empty_company(client: TestClient):
    data = _get_dashboard(client)
    assert data["inbox_unread"] == 0
    assert data["invoices_outstanding"] == 0.0
    assert data["projects_active"] == 0


# --- Indbakke ---

def test_dashboard_inbox_unread(client: TestClient):
    client.post("/inbox/", json={
        "source": "email",
        "received_at": f"{_today()}T09:00:00", "subject": "Spørgsmål",
    })
    client.post("/inbox/", json={
        "source": "phone",
        "received_at": f"{_today()}T10:00:00",
    })
    data = _get_dashboard(client)
    assert data["inbox_unread"] == 2


def test_dashboard_inbox_excludes_read(client: TestClient):
    r = client.post("/inbox/", json={
        "source": "email",
        "received_at": f"{_today()}T09:00:00",
    })
    client.post(f"/inbox/{r.json()['id']}/read")
    assert _get_dashboard(client)["inbox_unread"] == 0


# --- Henvendelser ---

def test_dashboard_enquiry_counts(client: TestClient):
    enq1 = client.post("/enquiries/", json={
        "title": "Forespørgsel 1", "source": "phone",
    }).json()
    client.post("/enquiries/", json={"title": "Forespørgsel 2", "source": "email"})
    client.post(f"/enquiries/{enq1['id']}/qualify")
    data = _get_dashboard(client)
    assert data["enquiries_new"] == 1
    assert data["enquiries_qualified"] == 1


# --- Projekter ---

def test_dashboard_project_counts(client: TestClient):
    cid, _ = _setup(client)
    pid = client.post("/projects/", json={"title": "Aktiv sag", "customer_id": cid}).json()["id"]
    client.post("/projects/", json={"title": "Kladde sag", "customer_id": cid})
    client.patch(f"/projects/{pid}", json={"status": "active"})
    data = _get_dashboard(client)
    assert data["projects_draft"] == 1
    assert data["projects_active"] == 1


# --- Tilbud ---

def test_dashboard_quotes_awaiting(client: TestClient):
    cid, _ = _setup(client)
    pid = client.post("/projects/", json={"title": "Sag", "customer_id": cid}).json()["id"]
    q = client.post("/quotes/", json={
        "project_id": pid, "title": "Tilbud",
        "quote_type": "line",
        "valid_until": _days(30), "lines": [],
    }).json()
    client.post(f"/quotes/{q['id']}/send")
    assert _get_dashboard(client)["quotes_awaiting"] == 1


# --- Fakturaer ---

def test_dashboard_invoices_draft_count(client: TestClient):
    cid, _ = _setup(client)
    pid = client.post("/projects/", json={"title": "Sag", "customer_id": cid}).json()["id"]
    client.post("/invoices/", json={
        "project_id": pid, "title": "Faktura",
        "issue_date": _today(), "due_date": _days(30),
    })
    assert _get_dashboard(client)["invoices_draft"] == 1


def test_dashboard_invoices_outstanding(client: TestClient):
    cid, _ = _setup(client)
    pid = client.post("/projects/", json={"title": "Sag", "customer_id": cid}).json()["id"]
    inv = client.post("/invoices/", json={
        "project_id": pid, "title": "Faktura",
        "issue_date": _today(), "due_date": _days(30),
        "lines": [{"description": "Arbejde", "quantity": 1.0, "unit_price": 4000.0}],
    }).json()
    client.post(f"/invoices/{inv['id']}/send")
    data = _get_dashboard(client)
    assert data["invoices_outstanding"] == 5000.0


def test_dashboard_overdue_invoices(client: TestClient):
    cid, _ = _setup(client)
    pid = client.post("/projects/", json={"title": "Sag", "customer_id": cid}).json()["id"]
    inv = client.post("/invoices/", json={
        "project_id": pid, "title": "Forfaldsfaktura",
        "issue_date": _days(-60), "due_date": _days(-30),
        "lines": [{"description": "Arbejde", "quantity": 1.0, "unit_price": 2000.0}],
    }).json()
    client.post(f"/invoices/{inv['id']}/send")
    data = _get_dashboard(client)
    assert data["invoices_overdue_count"] == 1
    assert data["invoices_overdue_amount"] == 2500.0


def test_dashboard_paid_invoice_not_overdue(client: TestClient):
    cid, _ = _setup(client)
    pid = client.post("/projects/", json={"title": "Sag", "customer_id": cid}).json()["id"]
    inv = client.post("/invoices/", json={
        "project_id": pid, "title": "Betalt",
        "issue_date": _days(-60), "due_date": _days(-30),
        "lines": [{"description": "Arbejde", "quantity": 1.0, "unit_price": 1000.0}],
    }).json()
    client.post(f"/invoices/{inv['id']}/send")
    client.post(f"/invoices/{inv['id']}/pay")
    data = _get_dashboard(client)
    assert data["invoices_overdue_count"] == 0


# --- Påmindelser ---

def test_dashboard_reminders_pending(client: TestClient):
    client.post("/reminders/", json={"title": "Opfølgning", "due_date": _days(3)})
    assert _get_dashboard(client)["reminders_pending"] == 1


# --- Admin Deadlines ---

def test_dashboard_overdue_deadlines(client: TestClient):
    client.post("/admin-deadlines/", json={
        "title": "Forfalden moms", "category": "vat_report", "due_date": _days(-5),
    })
    data = _get_dashboard(client)
    assert len(data["deadlines_overdue"]) == 1
    assert data["deadlines_overdue"][0]["title"] == "Forfalden moms"


def test_dashboard_upcoming_deadlines(client: TestClient):
    client.post("/admin-deadlines/", json={
        "title": "Kommende moms", "category": "vat_report", "due_date": _days(7),
    })
    client.post("/admin-deadlines/", json={
        "title": "Langt ude", "category": "vat_report", "due_date": _days(60),
    })
    data = _get_dashboard(client)
    titles = [d["title"] for d in data["deadlines_upcoming"]]
    assert "Kommende moms" in titles
    assert "Langt ude" not in titles


def test_dashboard_completed_deadline_not_in_overdue(client: TestClient):
    dl = client.post("/admin-deadlines/", json={
        "title": "Udført", "category": "vat_report", "due_date": _days(-5),
    }).json()
    client.post(f"/admin-deadlines/{dl['id']}/complete")
    assert len(_get_dashboard(client)["deadlines_overdue"]) == 0


# --- Reconciliation KPIs ---

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_dashboard_reconciliation_unmatched_count(client: TestClient):
    fp = str(_FIXTURES / "economic_invoices_sample.csv")
    r = client.post(f"/economic-invoices/import?file_path={fp}")
    assert r.status_code == 201
    data = _get_dashboard(client)
    assert data["reconciliation_unmatched_invoices"] == 5


def test_dashboard_reconciliation_overdue_count(client: TestClient):
    fp = str(_FIXTURES / "economic_invoices_sample.csv")
    client.post(f"/economic-invoices/import?file_path={fp}")
    data = _get_dashboard(client)
    assert data["reconciliation_overdue_invoices"] == 5


def test_dashboard_reconciliation_overdue_amount(client: TestClient):
    fp = str(_FIXTURES / "economic_invoices_sample.csv")
    client.post(f"/economic-invoices/import?file_path={fp}")
    data = _get_dashboard(client)
    assert data["reconciliation_overdue_amount_ore"] == 2770050
