from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str, str]:
    """Returns (company_id, project_id, customer_id)."""
    vid = client.post("/companies/", json={
        "name": "PLL Malerfirma ApS",
        "address": "Malervejen 5, 2100 København Ø",
        "cvr": "12345678",
    }).json()["id"]
    cid = client.post("/customers/", json={
        "name": "Familie Hansen",
        "address": "Villavej 12, 2900 Hellerup",
        "company_id": vid,
    }).json()["id"]
    pid = client.post("/projects/", json={
        "title": "Malingsarbejde stue + køkken",
        "customer_id": cid,
    }).json()["id"]
    return vid, pid, cid


def _make_invoice(client: TestClient, pid: str) -> dict:
    return client.post("/invoices/", json={
        "project_id": pid,
        "title": "Faktura – Malingsarbejde",
        "issue_date": "2026-05-20",
        "due_date": "2026-06-20",
        "notes": "Betal til reg. 1234 konto 56789012",
        "lines": [
            {"description": "Malerarbejde stue", "unit": "time", "quantity": 8.0, "unit_price": 650.0},
            {"description": "Malerarbejde køkken", "unit": "time", "quantity": 4.0, "unit_price": 650.0},
            {"description": "Maling og materialer", "unit": "stk", "quantity": 1.0, "unit_price": 1200.0},
        ],
    }).json()


def _make_quote(client: TestClient, pid: str) -> dict:
    return client.post("/quotes/", json={
        "project_id": pid,
        "title": "Tilbud – Malingsarbejde",
        "quote_type": "line",
        "valid_until": "2026-06-15",
        "notes": "Prisen er inkl. moms og alle materialer",
        "lines": [
            {"description": "Malerarbejde stue", "unit": "time", "quantity": 8.0, "unit_price": 650.0},
            {"description": "Malerarbejde køkken", "unit": "time", "quantity": 4.0, "unit_price": 650.0},
            {"description": "Maling og materialer", "unit": "stk", "quantity": 1.0, "unit_price": 1200.0},
        ],
    }).json()


# --- Faktura PDF ---

def test_invoice_pdf_status_ok(client: TestClient):
    _, pid, _ = _setup(client)
    inv = _make_invoice(client, pid)
    r = client.get(f"/invoices/{inv['id']}/pdf")
    assert r.status_code == 200


def test_invoice_pdf_content_type(client: TestClient):
    _, pid, _ = _setup(client)
    inv = _make_invoice(client, pid)
    r = client.get(f"/invoices/{inv['id']}/pdf")
    assert r.headers["content-type"] == "application/pdf"


def test_invoice_pdf_valid_pdf_header(client: TestClient):
    _, pid, _ = _setup(client)
    inv = _make_invoice(client, pid)
    r = client.get(f"/invoices/{inv['id']}/pdf")
    assert r.content[:4] == b"%PDF"


def test_invoice_pdf_has_content(client: TestClient):
    _, pid, _ = _setup(client)
    inv = _make_invoice(client, pid)
    r = client.get(f"/invoices/{inv['id']}/pdf")
    assert len(r.content) > 1000  # ikke tom PDF


def test_invoice_pdf_not_found(client: TestClient):
    assert client.get("/invoices/ukendt/pdf").status_code == 404


def test_invoice_pdf_filename_header(client: TestClient):
    _, pid, _ = _setup(client)
    inv = _make_invoice(client, pid)
    r = client.get(f"/invoices/{inv['id']}/pdf")
    cd = r.headers.get("content-disposition", "")
    assert inv["invoice_number"] in cd


# --- Tilbud PDF ---

def test_quote_pdf_status_ok(client: TestClient):
    _, pid, _ = _setup(client)
    q = _make_quote(client, pid)
    r = client.get(f"/quotes/{q['id']}/pdf")
    assert r.status_code == 200


def test_quote_pdf_content_type(client: TestClient):
    _, pid, _ = _setup(client)
    q = _make_quote(client, pid)
    r = client.get(f"/quotes/{q['id']}/pdf")
    assert r.headers["content-type"] == "application/pdf"


def test_quote_pdf_valid_pdf_header(client: TestClient):
    _, pid, _ = _setup(client)
    q = _make_quote(client, pid)
    r = client.get(f"/quotes/{q['id']}/pdf")
    assert r.content[:4] == b"%PDF"


def test_quote_pdf_has_content(client: TestClient):
    _, pid, _ = _setup(client)
    q = _make_quote(client, pid)
    r = client.get(f"/quotes/{q['id']}/pdf")
    assert len(r.content) > 1000


def test_quote_pdf_not_found(client: TestClient):
    assert client.get("/quotes/ukendt/pdf").status_code == 404


def test_quote_pdf_filename_header(client: TestClient):
    _, pid, _ = _setup(client)
    q = _make_quote(client, pid)
    r = client.get(f"/quotes/{q['id']}/pdf")
    cd = r.headers.get("content-disposition", "")
    assert q["quote_number"] in cd


# --- Inaktiv faktura kan stadig generere PDF ---

def test_inactive_invoice_pdf_still_generates(client: TestClient):
    _, pid, _ = _setup(client)
    inv = _make_invoice(client, pid)
    client.delete(f"/invoices/{inv['id']}")
    r = client.get(f"/invoices/{inv['id']}/pdf")
    assert r.status_code == 200
