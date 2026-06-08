from fastapi.testclient import TestClient


def _post_deadline(client: TestClient, **extra) -> dict:
    payload = {
        "title": "Momsindberetning Q1",
        "category": "vat_report",
        "due_date": "2026-06-01",
        **extra,
    }
    r = client.post("/admin-deadlines/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse ---

def test_create_deadline_minimal(client: TestClient, company_id: str):
    data = _post_deadline(client)
    assert data["status"] == "pending"
    assert data["active"] is True
    assert data["company_id"] == company_id


def test_create_deadline_with_notes(client: TestClient):
    data = _post_deadline(client, notes="Husk bilag")
    assert data["notes"] == "Husk bilag"


def test_unknown_company_is_session_company(client: TestClient):
    # Without session cookie, 401 would be returned, but we have the override.
    # With session cookie (override), any create uses the session company — just check 201.
    data = _post_deadline(client)
    assert data["status"] == "pending"


def test_duplicate_id_rejected(client: TestClient):
    _post_deadline(client, **{"id": "fixed-dl"})
    r = client.post("/admin-deadlines/", json={
        "id": "fixed-dl", "title": "Duplikat",
        "category": "vat_report", "due_date": "2026-06-01",
    })
    assert r.status_code == 409


# --- Opdatering ---

def test_update_pending_deadline(client: TestClient):
    dl = _post_deadline(client)
    r = client.patch(f"/admin-deadlines/{dl['id']}", json={
        "title": "Opdateret", "due_date": "2026-07-01",
    })
    assert r.status_code == 200
    assert r.json()["title"] == "Opdateret"
    assert r.json()["due_date"] == "2026-07-01"


def test_update_completed_rejected(client: TestClient):
    dl = _post_deadline(client)
    client.post(f"/admin-deadlines/{dl['id']}/complete")
    r = client.patch(f"/admin-deadlines/{dl['id']}", json={"title": "Ny"})
    assert r.status_code == 409


def test_get_not_found(client: TestClient):
    assert client.get("/admin-deadlines/ukendt").status_code == 404


# --- Liste og filtrering ---

def test_list_deadlines(client: TestClient):
    _post_deadline(client)
    _post_deadline(client, category="salary_run", title="Løn jan")
    assert len(client.get("/admin-deadlines/").json()) == 2


def test_filter_by_category(client: TestClient):
    _post_deadline(client, category="vat_report")
    _post_deadline(client, category="salary_run", title="Løn")
    r = client.get("/admin-deadlines/?category=vat_report")
    assert len(r.json()) == 1


def test_filter_by_status(client: TestClient):
    dl = _post_deadline(client)
    _post_deadline(client, title="Anden")
    client.post(f"/admin-deadlines/{dl['id']}/complete")
    r = client.get("/admin-deadlines/?status=completed")
    assert len(r.json()) == 1


def test_filter_by_date_range(client: TestClient):
    _post_deadline(client, due_date="2026-03-01")
    _post_deadline(client, due_date="2026-09-01", title="Q3")
    r = client.get("/admin-deadlines/?due_from=2026-01-01&due_to=2026-06-30")
    assert len(r.json()) == 1


# --- Status-overgange ---

def test_complete_deadline(client: TestClient):
    dl = _post_deadline(client)
    r = client.post(f"/admin-deadlines/{dl['id']}/complete")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_skip_deadline(client: TestClient):
    dl = _post_deadline(client)
    r = client.post(f"/admin-deadlines/{dl['id']}/skip")
    assert r.status_code == 200
    assert r.json()["status"] == "skipped"


def test_reopen_completed_deadline(client: TestClient):
    dl = _post_deadline(client)
    client.post(f"/admin-deadlines/{dl['id']}/complete")
    r = client.post(f"/admin-deadlines/{dl['id']}/reopen")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_reopen_skipped_deadline(client: TestClient):
    dl = _post_deadline(client)
    client.post(f"/admin-deadlines/{dl['id']}/skip")
    r = client.post(f"/admin-deadlines/{dl['id']}/reopen")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"


def test_invalid_complete_from_completed(client: TestClient):
    dl = _post_deadline(client)
    client.post(f"/admin-deadlines/{dl['id']}/complete")
    r = client.post(f"/admin-deadlines/{dl['id']}/complete")
    assert r.status_code == 409


# --- Generate-year ---

def test_generate_year_all_categories(client: TestClient):
    r = client.post("/admin-deadlines/generate-year", json={"year": 2026})
    assert r.status_code == 201
    items = r.json()
    assert len(items) > 0
    categories = {i["category"] for i in items}
    assert "vat_report" in categories


def test_generate_year_specific_categories(client: TestClient):
    r = client.post("/admin-deadlines/generate-year", json={
        "year": 2026,
        "categories": ["vat_report"],
    })
    assert r.status_code == 201
    items = r.json()
    assert all(i["category"] == "vat_report" for i in items)
    assert len(items) == 4  # 4 kvartaler


def test_generate_year_salary_run_creates_12(client: TestClient):
    r = client.post("/admin-deadlines/generate-year", json={
        "year": 2026,
        "categories": ["salary_run"],
    })
    assert r.status_code == 201
    assert len(r.json()) == 12  # en per måned


def test_generate_year_idempotent(client: TestClient):
    payload = {"year": 2026, "categories": ["vat_report"]}
    r1 = client.post("/admin-deadlines/generate-year", json=payload)
    r2 = client.post("/admin-deadlines/generate-year", json=payload)
    assert r1.status_code == 201
    assert r2.status_code == 201
    all_dl = client.get("/admin-deadlines/?category=vat_report").json()
    assert len(all_dl) == 4


# --- Soft-delete ---

def test_deactivate_deadline(client: TestClient):
    dl = _post_deadline(client)
    assert client.delete(f"/admin-deadlines/{dl['id']}").status_code == 204
    assert all(d["id"] != dl["id"] for d in client.get("/admin-deadlines/").json())
    direct = client.get(f"/admin-deadlines/{dl['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False
