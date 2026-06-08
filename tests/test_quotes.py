from fastapi.testclient import TestClient


def _make_customer(client: TestClient) -> str:
    vid = client.post("/companies/", json={"name": "Test Firma"}).json()["id"]
    r = client.post("/customers/", json={"name": "Test Kunde", "company_id": vid})
    assert r.status_code == 201
    return r.json()["id"]


def _make_project(client: TestClient, customer_id: str) -> str:
    r = client.post("/projects/", json={"title": "Test Projekt", "customer_id": customer_id})
    assert r.status_code == 201
    return r.json()["id"]


def _make_quote(client: TestClient, project_id: str, **extra) -> dict:
    payload = {"title": "Test Tilbud", "project_id": project_id, "quote_type": "line", **extra}
    r = client.post("/quotes/", json=payload)
    assert r.status_code == 201
    return r.json()


# --- Oprettelse ---

def test_create_quote_basic(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    data = _make_quote(client, pid)
    assert data["title"] == "Test Tilbud"
    assert data["project_id"] == pid
    assert data["status"] == "draft"
    assert data["active"] is True
    assert "id" in data


def test_quote_number_format(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    data = _make_quote(client, pid)
    import re
    assert re.match(r"^TIL-\d{4}-\d{3}$", data["quote_number"])


def test_quote_number_increments(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q1 = _make_quote(client, pid)
    q2 = _make_quote(client, pid)
    n1 = int(q1["quote_number"].split("-")[2])
    n2 = int(q2["quote_number"].split("-")[2])
    assert n2 == n1 + 1


def test_create_quote_unknown_project(client: TestClient):
    r = client.post("/quotes/", json={"title": "Test", "project_id": "ukendt"})
    assert r.status_code == 422


def test_create_quote_inactive_project(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    client.delete(f"/projects/{pid}")
    r = client.post("/quotes/", json={"title": "Test", "project_id": pid})
    assert r.status_code == 422


def test_create_quote_missing_project_id(client: TestClient):
    r = client.post("/quotes/", json={"title": "Ingen projekt"})
    assert r.status_code == 422


# --- Linjepositioner og momsberegning ---

def test_create_quote_with_lines(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    data = _make_quote(client, pid, lines=[
        {"description": "Fliser", "unit": "m2", "quantity": 20.0, "unit_price": 150.0},
        {"description": "Arbejdsløn", "unit": "time", "quantity": 8.0, "unit_price": 650.0},
    ])
    # subtotal = 20*150 + 8*650 = 3000 + 5200 = 8200
    assert data["subtotal"] == 8200.0
    # vat = 8200 * 0.25 = 2050
    assert data["vat_amount"] == 2050.0
    # total = 8200 + 2050 = 10250
    assert data["total"] == 10250.0
    assert len(data["lines"]) == 2
    assert data["lines"][0]["line_total"] == 3000.0


def test_vat_always_server_calculated(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    data = _make_quote(client, pid, lines=[
        {"description": "Test", "unit": "stk", "quantity": 1.0, "unit_price": 100.0},
    ])
    assert data["vat_amount"] == 25.0
    assert data["total"] == 125.0


# --- Opmåling (QuoteRoom) ---

def test_create_quote_with_rooms(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    r = client.post("/quotes/", json={
        "title": "Test Tilbud",
        "project_id": pid,
        "quote_type": "area",
        "rooms": [{"name": "Stue", "length_m": 5.0, "width_m": 4.0, "height_m": 2.5, "price_per_m2": 100.0}],
    })
    assert r.status_code == 201
    data = r.json()
    assert len(data["rooms"]) == 1
    room = data["rooms"][0]
    assert room["name"] == "Stue"
    # wall_m2 = 2 * (5+4) * 2.5 = 45.0
    assert room["wall_m2"] == 45.0
    # ceiling_m2 = 5*4 = 20.0
    assert room["ceiling_m2"] == 20.0
    assert room["floor_m2"] == 20.0
    # ingen fradrag
    assert room["wall_m2_net"] == 45.0


def test_room_m2_deductions(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    r = client.post("/quotes/", json={
        "title": "Test Tilbud",
        "project_id": pid,
        "quote_type": "area",
        "rooms": [{
            "name": "Soveværelse",
            "length_m": 4.0, "width_m": 3.0, "height_m": 2.5,
            "window_m2": 2.0, "door_m2": 1.75,
            "price_per_m2": 100.0,
        }],
    })
    assert r.status_code == 201
    room = r.json()["rooms"][0]
    # wall_m2 = 2*(4+3)*2.5 = 35.0
    assert room["wall_m2"] == 35.0
    # wall_m2_net = 35 - 2 - 1.75 = 31.25
    assert room["wall_m2_net"] == 31.25


def test_wall_m2_net_never_negative(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    r = client.post("/quotes/", json={
        "title": "Test Tilbud",
        "project_id": pid,
        "quote_type": "area",
        "rooms": [{"name": "Tiny", "length_m": 1.0, "width_m": 1.0, "height_m": 2.0,
                   "window_m2": 999.0, "door_m2": 999.0, "price_per_m2": 100.0}],
    })
    assert r.status_code == 201
    assert r.json()["rooms"][0]["wall_m2_net"] == 0.0


# --- Liste og filtrering ---

def test_list_quotes(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    _make_quote(client, pid)
    _make_quote(client, pid)
    r = client.get("/quotes/")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_quotes_filter_project(client: TestClient):
    cid = _make_customer(client)
    pid1 = _make_project(client, cid)
    pid2 = _make_project(client, cid)
    _make_quote(client, pid1)
    _make_quote(client, pid2)
    r = client.get(f"/quotes/?project_id={pid1}")
    assert len(r.json()) == 1


def test_list_quotes_filter_status(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    _make_quote(client, pid)
    client.post(f"/quotes/{q['id']}/send")
    r = client.get("/quotes/?status=sent")
    assert len(r.json()) == 1
    assert r.json()[0]["status"] == "sent"


# --- Hent enkelt ---

def test_get_quote(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    r = client.get(f"/quotes/{q['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == q["id"]


def test_get_quote_not_found(client: TestClient):
    r = client.get("/quotes/ukendt-id")
    assert r.status_code == 404


# --- PATCH ---

def test_patch_draft_quote(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    r = client.patch(f"/quotes/{q['id']}", json={"title": "Opdateret Titel"})
    assert r.status_code == 200
    assert r.json()["title"] == "Opdateret Titel"


def test_patch_sent_quote_rejected(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    client.post(f"/quotes/{q['id']}/send")
    r = client.patch(f"/quotes/{q['id']}", json={"title": "Forsøg"})
    assert r.status_code == 409


def test_patch_replaces_lines_and_recalculates(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid, lines=[
        {"description": "Gammel linje", "unit": "stk", "quantity": 1.0, "unit_price": 100.0},
    ])
    assert q["total"] == 125.0
    r = client.patch(f"/quotes/{q['id']}", json={"lines": [
        {"description": "Ny linje", "unit": "m2", "quantity": 10.0, "unit_price": 200.0},
    ]})
    assert r.status_code == 200
    data = r.json()
    assert data["subtotal"] == 2000.0
    assert data["total"] == 2500.0
    assert len(data["lines"]) == 1


# --- Statusovergange ---

def test_send_quote(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/send")
    assert r.status_code == 200
    assert r.json()["status"] == "sent"


def test_accept_quote(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    client.post(f"/quotes/{q['id']}/send")
    r = client.post(f"/quotes/{q['id']}/accept")
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"


def test_reject_quote(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    client.post(f"/quotes/{q['id']}/send")
    r = client.post(f"/quotes/{q['id']}/reject")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"


def test_invalid_transition_accept_draft(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    r = client.post(f"/quotes/{q['id']}/accept")
    assert r.status_code == 409


def test_accept_quote_activates_draft_project(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    assert client.get(f"/projects/{pid}").json()["status"] == "draft"
    q = _make_quote(client, pid)
    client.post(f"/quotes/{q['id']}/send")
    client.post(f"/quotes/{q['id']}/accept")
    assert client.get(f"/projects/{pid}").json()["status"] == "active"


def test_accept_quote_does_not_regress_active_project(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    client.patch(f"/projects/{pid}", json={"status": "active"})
    q = _make_quote(client, pid)
    client.post(f"/quotes/{q['id']}/send")
    client.post(f"/quotes/{q['id']}/accept")
    assert client.get(f"/projects/{pid}").json()["status"] == "active"


# --- Soft-delete ---

def test_deactivate_quote(client: TestClient):
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    q = _make_quote(client, pid)
    r = client.delete(f"/quotes/{q['id']}")
    assert r.status_code == 204
    assert all(x["id"] != q["id"] for x in client.get("/quotes/").json())
    direct = client.get(f"/quotes/{q['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


# --- Phase 4: quote_type enforcement ---

def test_quote_type_required_on_create(client: TestClient):
    """Creating a quote without quote_type returns 422."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    r = client.post("/quotes/", json={"title": "Intet type", "project_id": pid})
    assert r.status_code == 422


def test_line_quote_rejects_rooms(client: TestClient):
    """POST /quotes/ with quote_type='line' and non-empty rooms returns 422."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    r = client.post("/quotes/", json={
        "title": "Linjetilbud med rum",
        "project_id": pid,
        "quote_type": "line",
        "rooms": [{"name": "Stue", "length_m": 5.0, "width_m": 4.0, "height_m": 2.5}],
    })
    assert r.status_code == 422


def test_area_quote_rejects_lines(client: TestClient):
    """POST /quotes/ with quote_type='area' and non-empty lines returns 422."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    r = client.post("/quotes/", json={
        "title": "Arealtilbud med linjer",
        "project_id": pid,
        "quote_type": "area",
        "lines": [{"description": "Fliser", "unit": "m2", "quantity": 10.0, "unit_price": 100.0}],
    })
    assert r.status_code == 422


def test_area_quote_missing_price_per_m2_returns_422(client: TestClient):
    """POST /quotes/ with quote_type='area' and a room missing price_per_m2 returns 422."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    r = client.post("/quotes/", json={
        "title": "Arealtilbud uden pris",
        "project_id": pid,
        "quote_type": "area",
        "rooms": [{"name": "Stue", "length_m": 5.0, "width_m": 4.0, "height_m": 2.5}],
    })
    assert r.status_code == 422


def test_area_quote_totals_computed_from_rooms(client: TestClient):
    """Area quote subtotal = sum of (m2 * price_per_m2) across rooms."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    # room 1: 5*4 = 20 m2 floor, but area quote uses price_per_m2 * m2
    # We supply m2 directly via the area field calculation.
    # price_per_m2=100 applied to length_m*width_m area = 5*4=20 m2 => 2000
    # room 2: 3*3=9 m2, price_per_m2=50 => 450
    # total subtotal = 2450, vat=612.50, total=3062.50
    r = client.post("/quotes/", json={
        "title": "Arealtilbud",
        "project_id": pid,
        "quote_type": "area",
        "rooms": [
            {"name": "Stue", "length_m": 5.0, "width_m": 4.0, "height_m": 2.5, "price_per_m2": 100.0},
            {"name": "Køkken", "length_m": 3.0, "width_m": 3.0, "height_m": 2.5, "price_per_m2": 50.0},
        ],
    })
    assert r.status_code == 201
    data = r.json()
    assert data["quote_type"] == "area"
    # subtotal = 20*100 + 9*50 = 2000 + 450 = 2450
    assert data["subtotal"] == 2450.0
    assert data["vat_amount"] == 612.5
    assert data["total"] == 3062.5


def test_line_quote_totals_unchanged(client: TestClient):
    """Line quote totals computed from lines — unchanged from before."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    data = _make_quote(client, pid, lines=[
        {"description": "Fliser", "unit": "m2", "quantity": 10.0, "unit_price": 200.0},
    ])
    assert data["quote_type"] == "line"
    assert data["subtotal"] == 2000.0
    assert data["vat_amount"] == 500.0
    assert data["total"] == 2500.0


def test_patch_quote_type_change_clears_incompatible(client: TestClient):
    """PATCH changing quote_type clears the incompatible collection."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    # Create an area quote with rooms
    r = client.post("/quotes/", json={
        "title": "Arealtilbud til skift",
        "project_id": pid,
        "quote_type": "area",
        "rooms": [
            {"name": "Stue", "length_m": 5.0, "width_m": 4.0, "height_m": 2.5, "price_per_m2": 100.0},
        ],
    })
    assert r.status_code == 201
    qid = r.json()["id"]
    # Patch to type 'line' — rooms should be cleared
    pr = client.patch(f"/quotes/{qid}", json={"quote_type": "line"})
    assert pr.status_code == 200
    data = pr.json()
    assert data["quote_type"] == "line"
    assert data["rooms"] == []


def test_patch_area_quote_missing_price_per_m2_returns_422(client: TestClient):
    """PATCH area quote with room missing price_per_m2 returns 422."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    # Create a valid area quote first
    r = client.post("/quotes/", json={
        "title": "Arealtilbud",
        "project_id": pid,
        "quote_type": "area",
        "rooms": [{"name": "Stue", "length_m": 5.0, "width_m": 4.0, "height_m": 2.5, "price_per_m2": 100.0}],
    })
    assert r.status_code == 201
    qid = r.json()["id"]
    # PATCH with a room missing price_per_m2 — must be rejected before any room is persisted
    pr = client.patch(f"/quotes/{qid}", json={
        "rooms": [
            {"name": "Køkken", "length_m": 3.0, "width_m": 3.0, "height_m": 2.5},
        ],
    })
    assert pr.status_code == 422
    assert "price_per_m2" in pr.json()["detail"]


def test_accept_area_quote_generates_invoice_with_room_lines(client: TestClient):
    """Accepting an area quote auto-generates invoice lines from rooms."""
    cid = _make_customer(client)
    pid = _make_project(client, cid)
    # Create area quote: room 5m x 4m = 20 m2 @ 100 kr/m2 => subtotal 2000
    r = client.post("/quotes/", json={
        "title": "Maleropgave",
        "project_id": pid,
        "quote_type": "area",
        "rooms": [
            {"name": "Stue", "length_m": 5.0, "width_m": 4.0, "height_m": 2.5, "price_per_m2": 100.0},
        ],
    })
    assert r.status_code == 201
    quote = r.json()
    assert quote["subtotal"] == 2000.0

    # Send then accept
    client.post(f"/quotes/{quote['id']}/send")
    ar = client.post(f"/quotes/{quote['id']}/accept")
    assert ar.status_code == 200
    accepted = ar.json()
    assert accepted["status"] == "accepted"

    # Invoice must have been created (invoice_id populated)
    invoice_id = accepted["invoice_id"]
    assert invoice_id is not None

    # Fetch the invoice and verify lines and totals
    inv_r = client.get(f"/invoices/{invoice_id}")
    assert inv_r.status_code == 200
    inv = inv_r.json()

    # Subtotal must be non-zero — area quote had subtotal 2000
    assert inv["subtotal"] == 2000.0
    assert inv["vat_amount"] == 500.0
    assert inv["total"] == 2500.0

    # Lines must reflect rooms: one line for "Stue", qty=20 m2, unit_price=100
    assert len(inv["lines"]) == 1
    line = inv["lines"][0]
    assert line["description"] == "Stue"
    assert line["quantity"] == 20.0
    assert line["unit_price"] == 100.0
    assert line["line_total"] == 2000.0
