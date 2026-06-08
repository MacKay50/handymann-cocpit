"""Quote-accept → auto-draft-invoice flow."""
from datetime import date, timedelta
from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str]:
    """Returns (company_id, project_id)."""
    vid = client.post("/companies/", json={"name": "Firma"}).json()["id"]
    cid = client.post("/customers/", json={"name": "Kunde", "company_id": vid}).json()["id"]
    pid = client.post("/projects/", json={"title": "Projekt", "customer_id": cid}).json()["id"]
    return vid, pid


def _make_sent_quote(client, pid):
    q = client.post("/quotes/", json={
        "project_id": pid,
        "title": "Tilbud på maling",
        "quote_type": "line",
        "valid_until": "2026-06-30",
        "lines": [
            {"description": "Stue", "unit": "time", "quantity": 8.0, "unit_price": 600.0},
            {"description": "Materialer", "unit": "stk", "quantity": 1.0, "unit_price": 400.0},
        ],
    }).json()
    client.post(f"/quotes/{q['id']}/send")
    return q


# ── Accept response ───────────────────────────────────────────────────────────

def test_accept_quote_returns_invoice_id(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    assert r.status_code == 200
    assert r.json()["invoice_id"] is not None


# ── Invoice created ───────────────────────────────────────────────────────────

def test_accept_creates_one_draft_invoice(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    client.post(f"/quotes/{q['id']}/accept")
    invoices = client.get(f"/invoices/?project_id={pid}").json()
    assert len(invoices) == 1
    assert invoices[0]["status"] == "draft"


def test_accept_invoice_is_retrievable(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv_id = r.json()["invoice_id"]
    inv = client.get(f"/invoices/{inv_id}").json()
    assert inv["id"] == inv_id
    assert inv["status"] == "draft"


def test_accept_invoice_project_id(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv = client.get(f"/invoices/{r.json()['invoice_id']}").json()
    assert inv["project_id"] == pid


# ── Lines ─────────────────────────────────────────────────────────────────────

def test_accept_invoice_line_count(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv = client.get(f"/invoices/{r.json()['invoice_id']}").json()
    assert len(inv["lines"]) == 2


def test_accept_invoice_lines_descriptions(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv = client.get(f"/invoices/{r.json()['invoice_id']}").json()
    descriptions = {ln["description"] for ln in inv["lines"]}
    assert descriptions == {"Stue", "Materialer"}


def test_accept_invoice_lines_quantities_and_prices(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv = client.get(f"/invoices/{r.json()['invoice_id']}").json()
    by_desc = {ln["description"]: ln for ln in inv["lines"]}
    assert by_desc["Stue"]["quantity"] == 8.0
    assert by_desc["Stue"]["unit_price"] == 600.0
    assert by_desc["Materialer"]["quantity"] == 1.0
    assert by_desc["Materialer"]["unit_price"] == 400.0


# ── Totals ────────────────────────────────────────────────────────────────────

def test_accept_invoice_totals_match_quote(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv = client.get(f"/invoices/{r.json()['invoice_id']}").json()
    assert inv["subtotal"] == q["subtotal"]
    assert inv["vat_amount"] == q["vat_amount"]
    assert inv["total"] == q["total"]


# ── Title ─────────────────────────────────────────────────────────────────────

def test_accept_invoice_title_contains_quote_title(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv = client.get(f"/invoices/{r.json()['invoice_id']}").json()
    assert q["title"] in inv["title"]


# ── Dates ─────────────────────────────────────────────────────────────────────

def test_accept_invoice_issue_date_is_today(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv = client.get(f"/invoices/{r.json()['invoice_id']}").json()
    assert inv["issue_date"] == date.today().isoformat()


def test_accept_invoice_due_date_30_days(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    inv = client.get(f"/invoices/{r.json()['invoice_id']}").json()
    expected = (date.today() + timedelta(days=30)).isoformat()
    assert inv["due_date"] == expected


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_accept_second_time_is_409(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    client.post(f"/quotes/{q['id']}/accept")
    r2 = client.post(f"/quotes/{q['id']}/accept")
    assert r2.status_code == 409


def test_accept_idempotent_no_duplicate_invoice(client: TestClient):
    _, pid = _setup(client)
    q = _make_sent_quote(client, pid)
    client.post(f"/quotes/{q['id']}/accept")
    client.post(f"/quotes/{q['id']}/accept")  # 409, but no second invoice
    invoices = client.get(f"/invoices/?project_id={pid}").json()
    assert len(invoices) == 1
