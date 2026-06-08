from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    """Returns dict with an invoice_id (company comes from session)."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"title": "P", "customer_id": cid}).json()["id"]
    inv = client.post("/invoices/", json={
        "project_id": pid, "title": "Faktura",
        "issue_date": "2026-05-20", "due_date": "2026-06-20",
    }).json()
    client.post(f"/invoices/{inv['id']}/send")
    return {"project_id": pid, "invoice_id": inv["id"]}


def _post_reminder(client: TestClient, **extra) -> dict:
    payload = {
        "title": "Husk at følge op",
        "due_date": "2026-06-01",
        **extra,
    }
    r = client.post("/reminders/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse ---

def test_create_reminder_minimal(client: TestClient, company_id: str):
    data = _post_reminder(client)
    assert data["title"] == "Husk at følge op"
    assert data["status"] == "pending"
    assert data["active"] is True
    assert data["company_id"] == company_id
    assert data["related_entity_type"] is None
    assert data["related_entity_id"] is None


def test_create_reminder_with_entity_link(client: TestClient):
    ctx = _setup(client)
    data = _post_reminder(
        client,
        related_entity_type="invoice",
        related_entity_id=ctx["invoice_id"],
    )
    assert data["related_entity_type"] == "invoice"
    assert data["related_entity_id"] == ctx["invoice_id"]


def test_entity_type_without_id_rejected(client: TestClient):
    r = client.post("/reminders/", json={
        "title": "Test",
        "due_date": "2026-06-01",
        "related_entity_type": "invoice",
    })
    assert r.status_code == 422


def test_entity_id_without_type_rejected(client: TestClient):
    ctx = _setup(client)
    r = client.post("/reminders/", json={
        "title": "Test",
        "due_date": "2026-06-01",
        "related_entity_id": ctx["invoice_id"],
    })
    assert r.status_code == 422


def test_duplicate_id_rejected(client: TestClient):
    _post_reminder(client, **{"id": "fixed-rem"})
    r = client.post("/reminders/", json={
        "id": "fixed-rem",
        "title": "Duplikat",
        "due_date": "2026-06-01",
    })
    assert r.status_code == 409


# --- Opdatering ---

def test_update_pending_reminder(client: TestClient):
    rem = _post_reminder(client)
    r = client.patch(f"/reminders/{rem['id']}", json={
        "title": "Opdateret titel",
        "due_date": "2026-07-15",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Opdateret titel"
    assert data["due_date"] == "2026-07-15"


def test_update_adds_entity_link(client: TestClient):
    ctx = _setup(client)
    rem = _post_reminder(client)
    r = client.patch(f"/reminders/{rem['id']}", json={
        "related_entity_type": "invoice",
        "related_entity_id": ctx["invoice_id"],
    })
    assert r.status_code == 200
    assert r.json()["related_entity_type"] == "invoice"


def test_update_partial_entity_link_rejected(client: TestClient):
    rem = _post_reminder(client)
    r = client.patch(f"/reminders/{rem['id']}", json={
        "related_entity_type": "invoice",
    })
    assert r.status_code == 422


def test_update_acknowledged_reminder_rejected(client: TestClient):
    rem = _post_reminder(client)
    client.post(f"/reminders/{rem['id']}/acknowledge")
    r = client.patch(f"/reminders/{rem['id']}", json={"title": "Nyt"})
    assert r.status_code == 409


def test_get_reminder_not_found(client: TestClient):
    assert client.get("/reminders/ukendt").status_code == 404


# --- Liste og filtrering ---

def test_list_reminders(client: TestClient):
    _post_reminder(client)
    _post_reminder(client)
    assert len(client.get("/reminders/").json()) == 2


def test_filter_by_status(client: TestClient):
    rem = _post_reminder(client)
    _post_reminder(client)
    client.post(f"/reminders/{rem['id']}/acknowledge")
    r = client.get("/reminders/?status=acknowledged")
    assert len(r.json()) == 1


def test_filter_by_entity_type(client: TestClient):
    ctx = _setup(client)
    _post_reminder(
        client,
        related_entity_type="invoice",
        related_entity_id=ctx["invoice_id"],
    )
    _post_reminder(client)
    r = client.get("/reminders/?related_entity_type=invoice")
    assert len(r.json()) == 1


def test_filter_by_entity_id(client: TestClient):
    ctx = _setup(client)
    _post_reminder(
        client,
        related_entity_type="invoice",
        related_entity_id=ctx["invoice_id"],
    )
    _post_reminder(client)
    r = client.get(f"/reminders/?related_entity_id={ctx['invoice_id']}")
    assert len(r.json()) == 1


def test_filter_due_from(client: TestClient):
    _post_reminder(client, due_date="2026-05-01")
    _post_reminder(client, due_date="2026-08-01")
    r = client.get("/reminders/?due_from=2026-07-01")
    assert len(r.json()) == 1
    assert r.json()[0]["due_date"] == "2026-08-01"


def test_filter_due_to(client: TestClient):
    _post_reminder(client, due_date="2026-05-01")
    _post_reminder(client, due_date="2026-08-01")
    r = client.get("/reminders/?due_to=2026-06-01")
    assert len(r.json()) == 1
    assert r.json()[0]["due_date"] == "2026-05-01"


def test_list_excludes_inactive_by_default(client: TestClient):
    rem = _post_reminder(client)
    client.delete(f"/reminders/{rem['id']}")
    assert len(client.get("/reminders/").json()) == 0


# --- Kvittering (acknowledge) ---

def test_acknowledge_reminder(client: TestClient):
    rem = _post_reminder(client)
    r = client.post(f"/reminders/{rem['id']}/acknowledge")
    assert r.status_code == 200
    assert r.json()["status"] == "acknowledged"


def test_acknowledge_already_acknowledged_is_idempotent(client: TestClient):
    rem = _post_reminder(client)
    client.post(f"/reminders/{rem['id']}/acknowledge")
    r = client.post(f"/reminders/{rem['id']}/acknowledge")
    assert r.status_code == 200
    assert r.json()["status"] == "acknowledged"


def test_acknowledge_not_found(client: TestClient):
    assert client.post("/reminders/ukendt/acknowledge").status_code == 404


# --- Slet (blød) ---

def test_deactivate_reminder(client: TestClient):
    rem = _post_reminder(client)
    assert client.delete(f"/reminders/{rem['id']}").status_code == 204
    assert all(r["id"] != rem["id"] for r in client.get("/reminders/").json())
    direct = client.get(f"/reminders/{rem['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False
