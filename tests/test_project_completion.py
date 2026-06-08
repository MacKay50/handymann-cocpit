"""Tests for project completion-status and complete endpoint (Phase 7)."""
from fastapi.testclient import TestClient


# ── Helpers ───────────────────────────────────────────────────────────────────

def _setup(client: TestClient) -> tuple[str, str, str]:
    """Returns (customer_id, project_id, employee_id) for the session company."""
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    pid = client.post("/projects/", json={"title": "Projekt", "customer_id": cid}).json()["id"]
    eid = client.post(
        "/employees/", json={"name": "Lars", "default_hourly_rate": 500.0}
    ).json()["id"]
    return cid, pid, eid


def _post_time_entry(client: TestClient, pid: str, eid: str, billable: bool = True) -> dict:
    payload = {
        "project_id": pid,
        "employee_id": eid,
        "date": "2026-05-01",
        "hours": 2.0,
        "billable": billable,
    }
    r = client.post("/time-entries/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _post_expense(client: TestClient, pid: str, eid: str, billable: bool = True) -> dict:
    payload = {
        "project_id": pid,
        "employee_id": eid,
        "category": "materialer",
        "date": "2026-05-01",
        "amount_excl_vat": 100.0,
        "billable": billable,
    }
    r = client.post("/expenses/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _post_invoice(client: TestClient, pid: str) -> dict:
    payload = {
        "project_id": pid,
        "title": "Faktura",
        "issue_date": "2026-05-01",
        "due_date": "2026-05-15",
        "lines": [{"description": "Arbejde", "quantity": 1.0, "unit_price": 500.0}],
    }
    r = client.post("/invoices/", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_completion_status_all_clear(client: TestClient):
    """Project with no entries/invoices/action-items: ready=True."""
    _, pid, _ = _setup(client)
    r = client.get(f"/projects/{pid}/completion-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["blockers"] == []
    assert body["warnings"] == []


def test_completion_status_unbilled_entries_blocks(client: TestClient):
    """Unbilled billable TimeEntry → ready=False, blocker in list."""
    _, pid, eid = _setup(client)
    _post_time_entry(client, pid, eid, billable=True)

    r = client.get(f"/projects/{pid}/completion-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    types = [b["type"] for b in body["blockers"]]
    assert "unbilled_time_entries" in types


def test_completion_status_unbilled_expenses_blocks(client: TestClient):
    """Unbilled billable Expense → ready=False, blocker in list."""
    _, pid, eid = _setup(client)
    _post_expense(client, pid, eid, billable=True)

    r = client.get(f"/projects/{pid}/completion-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    types = [b["type"] for b in body["blockers"]]
    assert "unbilled_expenses" in types


def test_completion_status_unpaid_invoice_blocks(client: TestClient):
    """Invoice with status='sent' (not paid) → ready=False, blocker."""
    _, pid, _eid = _setup(client)
    inv = _post_invoice(client, pid)
    # Send but do NOT pay
    r = client.post(f"/invoices/{inv['id']}/send")
    assert r.status_code == 200

    r = client.get(f"/projects/{pid}/completion-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    types = [b["type"] for b in body["blockers"]]
    assert "no_paid_invoice" in types


def test_completion_status_open_action_items_warns(client: TestClient):
    """Open ActionItem → ready=True but warning in warnings list (soft, non-blocking)."""
    _, pid, _eid = _setup(client)
    # No blockers — but one open action item
    r = client.post("/action-items/", json={"title": "Åben opgave", "project_id": pid})
    assert r.status_code == 201

    r = client.get(f"/projects/{pid}/completion-status")
    assert r.status_code == 200
    body = r.json()
    # No blockers — open action items are warnings, not blockers
    assert body["ready"] is True
    assert body["blockers"] == []
    assert len(body["warnings"]) >= 1


def test_completion_status_non_billable_entries_no_block(client: TestClient):
    """Only non-billable (billable=False) time entries → ready=True (vacuous pass, RISK-05)."""
    _, pid, eid = _setup(client)
    _post_time_entry(client, pid, eid, billable=False)

    r = client.get(f"/projects/{pid}/completion-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["blockers"] == []


def test_complete_project_when_ready(client: TestClient):
    """POST /projects/{id}/complete when ready → 200, status='completed'."""
    _, pid, _ = _setup(client)
    r = client.post(f"/projects/{pid}/complete", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["close_override"] is False


def test_complete_project_blocked_no_reason_returns_422(client: TestClient):
    """POST /projects/{id}/complete when blocked and no close_reason → 422."""
    _, pid, eid = _setup(client)
    _post_time_entry(client, pid, eid, billable=True)  # creates a blocker

    r = client.post(f"/projects/{pid}/complete", json={})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "blockers" in detail
    assert len(detail["blockers"]) >= 1


def test_complete_project_with_close_reason_overrides(client: TestClient):
    """POST /projects/{id}/complete with close_reason → 200, close_override=True."""
    _, pid, eid = _setup(client)
    _post_time_entry(client, pid, eid, billable=True)  # creates a blocker

    r = client.post(f"/projects/{pid}/complete", json={"close_reason": "Afsluttet manuelt."})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["close_override"] is True
    assert body["close_reason"] == "Afsluttet manuelt."


def test_patch_projects_still_works(client: TestClient):
    """PATCH /projects/{id} is unchanged — still sets status=completed without checklist."""
    _, pid, eid = _setup(client)
    _post_time_entry(client, pid, eid, billable=True)  # would block via /complete

    # PATCH must still work unconditionally — the ORM path stays open (IMPACT-05)
    r = client.patch(f"/projects/{pid}", json={"status": "completed"})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
