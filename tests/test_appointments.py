from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    """Returns dict with customer_id, project_id, employee_id (company_id comes from session)."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"title": "Projekt", "customer_id": cid}).json()["id"]
    eid = client.post("/employees/", json={
        "name": "Maler", "role": "maler", "default_hourly_rate": 350.0,
    }).json()["id"]
    return {"customer_id": cid, "project_id": pid, "employee_id": eid}


def _post_appointment(client: TestClient, **extra) -> dict:
    payload = {
        "title": "Møde",
        "start_datetime": "2026-06-01T09:00:00",
        "end_datetime": "2026-06-01T11:00:00",
        "appointment_type": "site_visit",
        **extra,
    }
    r = client.post("/appointments/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse og validering ---

def test_create_appointment_minimal(client: TestClient, company_id: str):
    data = _post_appointment(client)
    assert data["title"] == "Møde"
    assert data["status"] == "scheduled"
    assert data["active"] is True
    assert data["company_id"] == company_id
    assert data["project_id"] is None
    assert data["customer_id"] is None
    assert data["employee_id"] is None


def test_create_appointment_with_project(client: TestClient):
    ctx = _setup(client)
    data = _post_appointment(client, project_id=ctx["project_id"])
    assert data["project_id"] == ctx["project_id"]
    assert data["customer_id"] == ctx["customer_id"]


def test_create_appointment_with_all_links(client: TestClient):
    ctx = _setup(client)
    data = _post_appointment(client, project_id=ctx["project_id"], employee_id=ctx["employee_id"])
    assert data["project_id"] == ctx["project_id"]
    assert data["customer_id"] == ctx["customer_id"]
    assert data["employee_id"] == ctx["employee_id"]


def test_end_before_start_rejected(client: TestClient):
    r = client.post("/appointments/", json={
        "title": "Bad",
        "start_datetime": "2026-06-01T11:00:00",
        "end_datetime": "2026-06-01T09:00:00",
        "appointment_type": "meeting",
    })
    assert r.status_code == 422


def test_end_equals_start_allowed(client: TestClient):
    data = _post_appointment(
        client,
        start_datetime="2026-06-01T09:00:00",
        end_datetime="2026-06-01T09:00:00",
    )
    assert data["status"] == "scheduled"


def test_unknown_project_rejected(client: TestClient):
    r = client.post("/appointments/", json={
        "title": "T",
        "start_datetime": "2026-06-01T09:00:00",
        "end_datetime": "2026-06-01T10:00:00",
        "appointment_type": "other",
        "project_id": "ukendt",
    })
    assert r.status_code == 422


def test_inactive_project_rejected(client: TestClient):
    ctx = _setup(client)
    client.delete(f"/projects/{ctx['project_id']}")
    r = client.post("/appointments/", json={
        "title": "T",
        "start_datetime": "2026-06-01T09:00:00",
        "end_datetime": "2026-06-01T10:00:00",
        "appointment_type": "other",
        "project_id": ctx["project_id"],
    })
    assert r.status_code == 422


def test_unknown_employee_rejected(client: TestClient):
    r = client.post("/appointments/", json={
        "title": "T",
        "start_datetime": "2026-06-01T09:00:00",
        "end_datetime": "2026-06-01T10:00:00",
        "appointment_type": "other",
        "employee_id": "ukendt",
    })
    assert r.status_code == 422


def test_duplicate_id_rejected(client: TestClient):
    _post_appointment(client, **{"id": "fixed-apt"})
    r = client.post("/appointments/", json={
        "id": "fixed-apt",
        "title": "Duplikat",
        "start_datetime": "2026-06-01T09:00:00",
        "end_datetime": "2026-06-01T10:00:00",
        "appointment_type": "other",
    })
    assert r.status_code == 409


# --- Opdatering ---

def test_update_scheduled_appointment(client: TestClient):
    apt = _post_appointment(client)
    r = client.patch(f"/appointments/{apt['id']}", json={
        "title": "Opdateret",
        "start_datetime": "2026-07-01T10:00:00",
        "end_datetime": "2026-07-01T12:00:00",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Opdateret"
    assert "2026-07-01" in data["start_datetime"]


def test_update_completed_appointment_rejected(client: TestClient):
    apt = _post_appointment(client)
    client.post(f"/appointments/{apt['id']}/complete")
    r = client.patch(f"/appointments/{apt['id']}", json={"title": "Nyt"})
    assert r.status_code == 409


def test_update_date_end_before_start_rejected(client: TestClient):
    apt = _post_appointment(client)
    r = client.patch(f"/appointments/{apt['id']}", json={
        "start_datetime": "2026-06-10T12:00:00",
        "end_datetime": "2026-06-10T08:00:00",
    })
    assert r.status_code == 422


def test_get_appointment_not_found(client: TestClient):
    assert client.get("/appointments/ukendt").status_code == 404


# --- Liste og filtrering ---

def test_list_appointments(client: TestClient):
    _post_appointment(client)
    _post_appointment(client)
    assert len(client.get("/appointments/").json()) == 2


def test_filter_by_project_id(client: TestClient):
    ctx = _setup(client)
    _post_appointment(client, project_id=ctx["project_id"])
    _post_appointment(client)
    r = client.get(f"/appointments/?project_id={ctx['project_id']}")
    assert len(r.json()) == 1


def test_filter_by_employee_id(client: TestClient):
    ctx = _setup(client)
    _post_appointment(client, employee_id=ctx["employee_id"])
    _post_appointment(client)
    r = client.get(f"/appointments/?employee_id={ctx['employee_id']}")
    assert len(r.json()) == 1


def test_filter_by_status(client: TestClient):
    apt = _post_appointment(client)
    _post_appointment(client)
    client.post(f"/appointments/{apt['id']}/complete")
    r = client.get("/appointments/?status=completed")
    assert len(r.json()) == 1


def test_filter_by_date_from(client: TestClient):
    _post_appointment(client, start_datetime="2026-05-01T09:00:00", end_datetime="2026-05-01T10:00:00")
    _post_appointment(client, start_datetime="2026-07-01T09:00:00", end_datetime="2026-07-01T10:00:00")
    r = client.get("/appointments/?date_from=2026-06-01")
    assert len(r.json()) == 1
    assert "2026-07-01" in r.json()[0]["start_datetime"]


def test_filter_by_date_to(client: TestClient):
    _post_appointment(client, start_datetime="2026-05-01T09:00:00", end_datetime="2026-05-01T10:00:00")
    _post_appointment(client, start_datetime="2026-07-01T09:00:00", end_datetime="2026-07-01T10:00:00")
    r = client.get("/appointments/?date_to=2026-06-01")
    assert len(r.json()) == 1
    assert "2026-05-01" in r.json()[0]["start_datetime"]


# --- Status-overgange ---

def test_complete_appointment(client: TestClient):
    apt = _post_appointment(client)
    r = client.post(f"/appointments/{apt['id']}/complete")
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_cancel_appointment(client: TestClient):
    apt = _post_appointment(client)
    r = client.post(f"/appointments/{apt['id']}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_invalid_transition_from_completed(client: TestClient):
    apt = _post_appointment(client)
    client.post(f"/appointments/{apt['id']}/complete")
    r = client.post(f"/appointments/{apt['id']}/cancel")
    assert r.status_code == 409


def test_invalid_transition_from_cancelled(client: TestClient):
    apt = _post_appointment(client)
    client.post(f"/appointments/{apt['id']}/cancel")
    r = client.post(f"/appointments/{apt['id']}/complete")
    assert r.status_code == 409


# --- Slet (blød) ---

def test_deactivate_appointment(client: TestClient):
    apt = _post_appointment(client)
    assert client.delete(f"/appointments/{apt['id']}").status_code == 204
    assert all(a["id"] != apt["id"] for a in client.get("/appointments/").json())
    direct = client.get(f"/appointments/{apt['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False
