from fastapi.testclient import TestClient


def _setup_invoice(client: TestClient, unit_price: float = 1000.0, send: bool = True) -> dict:
    """Creates customer→project→invoice using session company. Returns full invoice dict."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"title": "P", "customer_id": cid}).json()["id"]
    inv = client.post("/invoices/", json={
        "project_id": pid,
        "title": "Faktura",
        "issue_date": "2026-05-20",
        "due_date": "2026-06-20",
        "lines": [{"description": "Arbejde", "quantity": 1.0, "unit_price": unit_price}],
    }).json()
    if send:
        inv = client.post(f"/invoices/{inv['id']}/send").json()
    return inv


def _post_payment(client: TestClient, invoice_id: str, amount: float = 100.0, **extra) -> dict:
    payload = {
        "invoice_id": invoice_id,
        "amount": amount,
        "payment_date": "2026-05-20",
        "method": "bank_transfer",
        **extra,
    }
    r = client.post("/payments/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse og afledning ---

def test_create_payment(client: TestClient):
    inv = _setup_invoice(client)
    data = _post_payment(client, inv["id"], amount=500.0)
    assert data["amount"] == 500.0
    assert data["method"] == "bank_transfer"
    assert data["active"] is True


def test_company_and_project_server_derived(client: TestClient):
    inv = _setup_invoice(client)
    data = _post_payment(client, inv["id"])
    assert data["company_id"] == inv["company_id"]
    assert data["project_id"] == inv["project_id"]
    assert data["invoice_id"] == inv["id"]


def test_amount_must_be_positive(client: TestClient):
    inv = _setup_invoice(client)
    r = client.post("/payments/", json={
        "invoice_id": inv["id"], "amount": 0.0,
        "payment_date": "2026-05-20", "method": "cash",
    })
    assert r.status_code == 422
    r2 = client.post("/payments/", json={
        "invoice_id": inv["id"], "amount": -5.0,
        "payment_date": "2026-05-20", "method": "cash",
    })
    assert r2.status_code == 422


def test_duplicate_id_rejected(client: TestClient):
    inv = _setup_invoice(client)
    _post_payment(client, inv["id"], **{"id": "fixed-pay"})
    r = client.post("/payments/", json={
        "id": "fixed-pay",
        "invoice_id": inv["id"],
        "amount": 50.0,
        "payment_date": "2026-05-20",
        "method": "cash",
    })
    assert r.status_code == 409


def test_unknown_invoice_rejected(client: TestClient):
    r = client.post("/payments/", json={
        "invoice_id": "ukendt",
        "amount": 100.0,
        "payment_date": "2026-05-20",
        "method": "cash",
    })
    assert r.status_code == 422


def test_payment_on_cancelled_invoice_rejected(client: TestClient):
    inv = _setup_invoice(client)
    client.post(f"/invoices/{inv['id']}/cancel")
    r = client.post("/payments/", json={
        "invoice_id": inv["id"], "amount": 100.0,
        "payment_date": "2026-05-20", "method": "cash",
    })
    assert r.status_code == 422


def test_payment_on_draft_invoice_allowed(client: TestClient):
    inv = _setup_invoice(client, send=False)
    data = _post_payment(client, inv["id"])
    assert data["active"] is True
    draft_status = client.get(f"/invoices/{inv['id']}").json()["status"]
    assert draft_status == "draft"


def test_payment_on_inactive_invoice_rejected(client: TestClient):
    inv = _setup_invoice(client)
    client.delete(f"/invoices/{inv['id']}")
    r = client.post("/payments/", json={
        "invoice_id": inv["id"], "amount": 100.0,
        "payment_date": "2026-05-20", "method": "cash",
    })
    assert r.status_code == 422


# --- Auto-overgang til betalt ---

def test_partial_payment_keeps_status_sent(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    _post_payment(client, inv["id"], amount=500.0)
    status = client.get(f"/invoices/{inv['id']}").json()["status"]
    assert status == "sent"


def test_full_payment_transitions_to_paid(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    _post_payment(client, inv["id"], amount=inv["total"])
    status = client.get(f"/invoices/{inv['id']}").json()["status"]
    assert status == "paid"


def test_overpayment_allowed_and_transitions_to_paid(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    _post_payment(client, inv["id"], amount=inv["total"] + 100.0)
    status = client.get(f"/invoices/{inv['id']}").json()["status"]
    assert status == "paid"


def test_multiple_partials_reaching_total(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    _post_payment(client, inv["id"], amount=700.0)
    assert client.get(f"/invoices/{inv['id']}").json()["status"] == "sent"
    _post_payment(client, inv["id"], amount=600.0)
    assert client.get(f"/invoices/{inv['id']}").json()["status"] == "paid"


def test_payment_on_already_paid_invoice_allowed(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    _post_payment(client, inv["id"], amount=inv["total"])
    data = _post_payment(client, inv["id"], amount=50.0)
    assert data["active"] is True
    assert client.get(f"/invoices/{inv['id']}").json()["status"] == "paid"


def test_draft_invoice_full_payment_no_auto_paid(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0, send=False)
    _post_payment(client, inv["id"], amount=inv["total"])
    status = client.get(f"/invoices/{inv['id']}").json()["status"]
    assert status == "draft"


# --- Append-only (ingen PATCH) ---

def test_patch_payment_returns_405(client: TestClient):
    inv = _setup_invoice(client)
    data = _post_payment(client, inv["id"])
    r = client.patch(f"/payments/{data['id']}", json={"amount": 999.0})
    assert r.status_code == 405


# --- Liste og filtrering ---

def test_list_payments(client: TestClient):
    inv = _setup_invoice(client)
    _post_payment(client, inv["id"])
    _post_payment(client, inv["id"])
    assert len(client.get("/payments/").json()) == 2


def test_filter_by_invoice_id(client: TestClient):
    inv1 = _setup_invoice(client)
    inv2 = _setup_invoice(client)
    _post_payment(client, inv1["id"])
    _post_payment(client, inv2["id"])
    r = client.get(f"/payments/?invoice_id={inv1['id']}")
    assert len(r.json()) == 1


def test_filter_by_project_id(client: TestClient):
    inv1 = _setup_invoice(client)
    inv2 = _setup_invoice(client)
    _post_payment(client, inv1["id"])
    _post_payment(client, inv2["id"])
    r = client.get(f"/payments/?project_id={inv1['project_id']}")
    assert len(r.json()) == 1


def test_list_returns_session_company_only(client: TestClient, company_id: str):
    # All payments in the list belong to the session company
    inv = _setup_invoice(client)
    _post_payment(client, inv["id"])
    r = client.get("/payments/")
    assert len(r.json()) == 1
    assert r.json()[0]["company_id"] == company_id


def test_list_excludes_inactive_by_default(client: TestClient):
    inv = _setup_invoice(client)
    data = _post_payment(client, inv["id"])
    client.delete(f"/payments/{data['id']}")
    assert len(client.get("/payments/").json()) == 0


# --- Summary ---

def test_summary_no_payments(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    r = client.get(f"/payments/summary?invoice_id={inv['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["total_paid"] == 0.0
    assert data["invoice_total"] == inv["total"]
    assert data["outstanding"] == inv["total"]
    assert data["overpaid"] == 0.0


def test_summary_partial(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    _post_payment(client, inv["id"], amount=500.0)
    data = client.get(f"/payments/summary?invoice_id={inv['id']}").json()
    assert data["total_paid"] == 500.0
    assert data["outstanding"] == 750.0
    assert data["overpaid"] == 0.0


def test_summary_full(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    _post_payment(client, inv["id"], amount=inv["total"])
    data = client.get(f"/payments/summary?invoice_id={inv['id']}").json()
    assert data["total_paid"] == inv["total"]
    assert data["outstanding"] == 0.0
    assert data["overpaid"] == 0.0


def test_summary_overpaid(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    overpay_amount = inv["total"] + 75.0
    _post_payment(client, inv["id"], amount=overpay_amount)
    data = client.get(f"/payments/summary?invoice_id={inv['id']}").json()
    assert data["outstanding"] == 0.0
    assert data["overpaid"] == 75.0


def test_summary_excludes_inactive_payments(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    pay = _post_payment(client, inv["id"], amount=inv["total"])
    client.delete(f"/payments/{pay['id']}")
    data = client.get(f"/payments/summary?invoice_id={inv['id']}").json()
    assert data["total_paid"] == 0.0
    assert data["outstanding"] == inv["total"]


def test_summary_unknown_invoice_422(client: TestClient):
    r = client.get("/payments/summary?invoice_id=ukendt")
    assert r.status_code == 422


# --- Enkelt og slet ---

def test_get_payment_not_found(client: TestClient):
    assert client.get("/payments/ukendt").status_code == 404


def test_deactivate_payment(client: TestClient):
    inv = _setup_invoice(client)
    data = _post_payment(client, inv["id"])
    assert client.delete(f"/payments/{data['id']}").status_code == 204
    assert all(p["id"] != data["id"] for p in client.get("/payments/").json())
    direct = client.get(f"/payments/{data['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


def test_deactivate_does_not_reverse_invoice_status(client: TestClient):
    inv = _setup_invoice(client, unit_price=1000.0)
    pay = _post_payment(client, inv["id"], amount=inv["total"])
    assert client.get(f"/invoices/{inv['id']}").json()["status"] == "paid"
    client.delete(f"/payments/{pay['id']}")
    assert client.get(f"/invoices/{inv['id']}").json()["status"] == "paid"
