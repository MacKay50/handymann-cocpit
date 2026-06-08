from fastapi.testclient import TestClient


def _setup(client: TestClient) -> tuple[str, str, str]:
    """Returns (customer_id, project_id, employee_id) for the session company."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"title": "Projekt", "customer_id": cid}).json()["id"]
    eid = client.post(
        "/employees/", json={"name": "Lars", "default_hourly_rate": 500.0}
    ).json()["id"]
    return cid, pid, eid


def _post_entry(client: TestClient, pid: str, eid: str, **extra) -> dict:
    payload = {
        "project_id": pid, "employee_id": eid,
        "date": "2026-05-20", "hours": 2.0,
        **extra,
    }
    r = client.post("/time-entries/", json=payload)
    assert r.status_code == 201
    return r.json()


def test_time_summary_groups_by_action_item(client: TestClient):
    """GET /projects/{id}/time-summary groups entries by action_item label."""
    _, pid, eid = _setup(client)
    ai_r = client.post("/action-items/", json={"title": "Maling", "project_id": pid})
    assert ai_r.status_code == 201
    ai_id = ai_r.json()["id"]

    _post_entry(client, pid, eid, hours=3.0, action_item_id=ai_id)
    _post_entry(client, pid, eid, hours=2.0, action_item_id=ai_id)

    r = client.get(f"/projects/{pid}/time-summary")
    assert r.status_code == 200
    groups = r.json()
    assert len(groups) == 1
    g = groups[0]
    assert g["action_item_id"] == ai_id
    assert g["label"] == "Maling"
    assert g["total_hours"] == 5.0
    assert len(g["entries"]) == 2


def test_time_summary_null_entries_under_generelt(client: TestClient):
    """Entries without action_item_id appear under label='Generelt'."""
    _, pid, eid = _setup(client)
    _post_entry(client, pid, eid, hours=4.0)
    _post_entry(client, pid, eid, hours=1.5)

    r = client.get(f"/projects/{pid}/time-summary")
    assert r.status_code == 200
    groups = r.json()
    assert len(groups) == 1
    g = groups[0]
    assert g["action_item_id"] is None
    assert g["label"] == "Generelt"
    assert g["total_hours"] == 5.5
    assert len(g["entries"]) == 2


def test_time_summary_mixed_entries(client: TestClient):
    """Mix of linked and unlinked entries groups correctly."""
    _, pid, eid = _setup(client)
    ai_r = client.post("/action-items/", json={"title": "Snedker", "project_id": pid})
    assert ai_r.status_code == 201
    ai_id = ai_r.json()["id"]

    _post_entry(client, pid, eid, hours=6.0, action_item_id=ai_id)
    _post_entry(client, pid, eid, hours=2.0)  # no action_item_id

    r = client.get(f"/projects/{pid}/time-summary")
    assert r.status_code == 200
    groups = r.json()
    assert len(groups) == 2

    by_label = {g["label"]: g for g in groups}
    assert "Snedker" in by_label
    assert "Generelt" in by_label
    assert by_label["Snedker"]["total_hours"] == 6.0
    assert by_label["Generelt"]["total_hours"] == 2.0
