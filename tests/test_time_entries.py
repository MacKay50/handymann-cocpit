from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str, str]:
    vid = client.post("/companies/", json={"name": "Test Firma"}).json()["id"]
    cid = client.post("/customers/", json={"name": "Kunde", "company_id": vid}).json()["id"]
    pid = client.post("/projects/", json={"title": "Projekt", "customer_id": cid}).json()["id"]
    eid = client.post(
        "/employees/", json={"name": "Lars", "default_hourly_rate": 650.0, "company_id": vid}
    ).json()["id"]
    return cid, pid, eid


def _post_entry(client: TestClient, pid: str, eid: str, **extra) -> dict:
    payload = {
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": 8.0,
        "description": "Maling", **extra,
    }
    r = client.post("/time-entries/", json=payload)
    assert r.status_code == 201
    return r.json()


# --- Oprettelse ---

def test_create_entry(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_entry(client, pid, eid)
    assert data["hours"] == 8.0
    assert data["employee_id"] == eid
    assert data["project_id"] == pid
    assert data["billable"] is True
    assert data["active"] is True


def test_total_uses_employee_default_rate(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_entry(client, pid, eid)
    # default_hourly_rate=650, hours=8 → total=5200
    assert data["hourly_rate"] == 650.0
    assert data["total"] == 5200.0


def test_hourly_rate_override(client: TestClient):
    _, pid, eid = _setup(client)
    data = _post_entry(client, pid, eid, hourly_rate=800.0)
    assert data["hourly_rate"] == 800.0
    assert data["total"] == 6400.0


def test_total_precision(client: TestClient):
    _, pid, eid = _setup(client)
    # 1.5 hours * 333.33 kr = 499.995 -> rounds to 500.00
    data = _post_entry(client, pid, eid, hours=1.5, hourly_rate=333.33)
    assert data["total"] == 500.00


def test_create_entry_unknown_project(client: TestClient):
    _, _, eid = _setup(client)
    r = client.post("/time-entries/", json={
        "project_id": "ukendt", "employee_id": eid,
        "date": "2026-05-20", "hours": 4.0,
    })
    assert r.status_code == 422


def test_create_entry_inactive_project(client: TestClient):
    _, pid, eid = _setup(client)
    client.delete(f"/projects/{pid}")
    r = client.post("/time-entries/", json={
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": 4.0,
    })
    assert r.status_code == 422


def test_create_entry_unknown_employee(client: TestClient):
    _, pid, _ = _setup(client)
    r = client.post("/time-entries/", json={
        "project_id": pid, "employee_id": "ukendt",
        "date": "2026-05-20", "hours": 4.0,
    })
    assert r.status_code == 422


def test_create_entry_inactive_employee(client: TestClient):
    _, pid, eid = _setup(client)
    client.delete(f"/employees/{eid}")
    r = client.post("/time-entries/", json={
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": 4.0,
    })
    assert r.status_code == 422


# --- Liste og filtrering ---

def test_list_entries(client: TestClient):
    _, pid, eid = _setup(client)
    _post_entry(client, pid, eid)
    _post_entry(client, pid, eid)
    assert len(client.get("/time-entries/").json()) == 2


def test_filter_by_project(client: TestClient):
    vid = client.post("/companies/", json={"name": "F"}).json()["id"]
    cid = client.post("/customers/", json={"name": "K", "company_id": vid}).json()["id"]
    pid1 = client.post("/projects/", json={"title": "P1", "customer_id": cid}).json()["id"]
    pid2 = client.post("/projects/", json={"title": "P2", "customer_id": cid}).json()["id"]
    eid = client.post(
        "/employees/", json={"name": "E", "default_hourly_rate": 600.0, "company_id": vid}
    ).json()["id"]
    _post_entry(client, pid1, eid)
    _post_entry(client, pid2, eid)
    r = client.get(f"/time-entries/?project_id={pid1}")
    assert len(r.json()) == 1


def test_filter_by_employee(client: TestClient):
    vid = client.post("/companies/", json={"name": "F"}).json()["id"]
    cid = client.post("/customers/", json={"name": "K", "company_id": vid}).json()["id"]
    pid = client.post("/projects/", json={"title": "P", "customer_id": cid}).json()["id"]
    eid1 = client.post(
        "/employees/", json={"name": "E1", "default_hourly_rate": 600.0, "company_id": vid}
    ).json()["id"]
    eid2 = client.post(
        "/employees/", json={"name": "E2", "default_hourly_rate": 700.0, "company_id": vid}
    ).json()["id"]
    _post_entry(client, pid, eid1)
    _post_entry(client, pid, eid2)
    r = client.get(f"/time-entries/?employee_id={eid1}")
    assert len(r.json()) == 1


# --- Summary ---

def test_summary(client: TestClient):
    _, pid, eid = _setup(client)
    _post_entry(client, pid, eid, hours=8.0)
    _post_entry(client, pid, eid, hours=4.0, billable=False)
    r = client.get(f"/time-entries/summary?project_id={pid}")
    assert r.status_code == 200
    data = r.json()
    # total: (8+4)*650 = 7800
    assert data["total_hours"] == 12.0
    assert data["total_cost"] == 7800.0
    # billable: 8*650 = 5200
    assert data["billable_hours"] == 8.0
    assert data["billable_cost"] == 5200.0


# --- Enkelt, opdater, slet ---

def test_summary_unknown_project(client: TestClient):
    r = client.get("/time-entries/summary?project_id=ukendt-id")
    assert r.status_code == 422


def test_get_entry_not_found(client: TestClient):
    assert client.get("/time-entries/ukendt").status_code == 404


def test_update_entry(client: TestClient):
    _, pid, eid = _setup(client)
    entry = _post_entry(client, pid, eid, hours=4.0)
    r = client.patch(f"/time-entries/{entry['id']}", json={"hours": 6.0})
    assert r.status_code == 200
    data = r.json()
    assert data["hours"] == 6.0
    assert data["total"] == 6.0 * 650.0


def test_deactivate_entry(client: TestClient):
    _, pid, eid = _setup(client)
    entry = _post_entry(client, pid, eid)
    assert client.delete(f"/time-entries/{entry['id']}").status_code == 204
    assert all(e["id"] != entry["id"] for e in client.get("/time-entries/").json())
    direct = client.get(f"/time-entries/{entry['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False


# --- Opgavekobling (action_item_id) ---

def _setup_with_action_item(client: TestClient) -> tuple[str, str, str, str]:
    """Returns (project_id, employee_id, action_item_id, other_project_id)."""
    _, pid, eid = _setup(client)
    ai_r = client.post("/action-items/", json={"title": "Mal væg", "project_id": pid})
    assert ai_r.status_code == 201
    ai_id = ai_r.json()["id"]

    # A second project (same customer — customer_id from pid)
    proj_r = client.get(f"/projects/{pid}")
    cust_id = proj_r.json()["customer_id"]
    r2 = client.post("/projects/", json={"title": "Andet Projekt", "customer_id": cust_id})
    pid2 = r2.json()["id"]
    return pid, eid, ai_id, pid2


def test_time_entry_with_action_item(client: TestClient):
    """POST /time-entries/ with valid action_item_id succeeds."""
    pid, eid, ai_id, _ = _setup_with_action_item(client)
    payload = {
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": 2.0,
        "action_item_id": ai_id,
    }
    r = client.post("/time-entries/", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["action_item_id"] == ai_id


def test_time_entry_wrong_project_action_item_rejected(client: TestClient):
    """action_item_id from a different project returns 422."""
    pid, eid, _, pid2 = _setup_with_action_item(client)
    # Create an action item belonging to pid2
    ai2_r = client.post("/action-items/", json={"title": "Anden opgave", "project_id": pid2})
    assert ai2_r.status_code == 201
    ai2_id = ai2_r.json()["id"]

    # Try to attach it to a time entry for pid (different project)
    payload = {
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": 3.0,
        "action_item_id": ai2_id,
    }
    r = client.post("/time-entries/", json=payload)
    assert r.status_code == 422
    assert "projekt" in r.json()["detail"].lower()


def test_time_entry_inactive_action_item_warns(client: TestClient):
    """action_item_id pointing to inactive ActionItem succeeds with warning in response."""
    pid, eid, ai_id, _ = _setup_with_action_item(client)
    # Soft-delete the action item
    client.delete(f"/action-items/{ai_id}")

    payload = {
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": 1.5,
        "action_item_id": ai_id,
    }
    r = client.post("/time-entries/", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["action_item_id"] == ai_id
    assert data.get("warning") is not None
    assert len(data["warning"]) > 0


def test_patch_time_entry_action_item_wrong_project_rejected(client: TestClient):
    """PATCH action_item_id from a different project returns 422."""
    pid, eid, _, pid2 = _setup_with_action_item(client)
    entry = _post_entry(client, pid, eid)
    ai2_r = client.post("/action-items/", json={"title": "Anden opgave", "project_id": pid2})
    ai2_id = ai2_r.json()["id"]
    r = client.patch(f"/time-entries/{entry['id']}", json={"action_item_id": ai2_id})
    assert r.status_code == 422
    assert "projekt" in r.json()["detail"].lower()


def test_patch_time_entry_inactive_action_item_warns(client: TestClient):
    """PATCH action_item_id pointing to inactive ActionItem succeeds with warning."""
    pid, eid, ai_id, _ = _setup_with_action_item(client)
    entry = _post_entry(client, pid, eid)
    client.delete(f"/action-items/{ai_id}")
    r = client.patch(f"/time-entries/{entry['id']}", json={"action_item_id": ai_id})
    assert r.status_code == 200
    assert r.json().get("warning") is not None


def test_patch_time_entry_clear_action_item(client: TestClient):
    """PATCH with action_item_id=null clears the link."""
    pid, eid, ai_id, _ = _setup_with_action_item(client)
    entry = _post_entry(client, pid, eid, action_item_id=ai_id)
    r = client.patch(f"/time-entries/{entry['id']}", json={"action_item_id": None})
    assert r.status_code == 200
    assert r.json()["action_item_id"] is None
