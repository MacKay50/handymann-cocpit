from __future__ import annotations
from fastapi.testclient import TestClient


# ── helpers ───────────────────────────────────────────────────────────────────

def _setup(client: TestClient) -> dict:
    """Creates customer→project→quote using session company."""
    cust = client.post("/customers/", json={"name": "Testkunse"}).json()
    proj = client.post("/projects/", json={
        "customer_id": cust["id"],
        "title": "Malerarbejde", "status": "draft",
    }).json()
    quote = client.post("/quotes/", json={
        "project_id": proj["id"],
        "title": "Tilbud på malerarbejde",
        "quote_type": "line",
        "lines": [{"description": "Maling af stue", "unit": "m2", "quantity": 30, "unit_price": 120}],
    }).json()
    return {"project_id": proj["id"], "quote_id": quote["id"]}


def _send(client: TestClient, quote_id: str) -> dict:
    r = client.post(f"/quotes/{quote_id}/send")
    assert r.status_code == 200, r.json()
    return r.json()


# ── token generated on send ───────────────────────────────────────────────────

def test_send_generates_accept_token(client: TestClient):
    ctx = _setup(client)
    data = _send(client, ctx["quote_id"])
    assert data["accept_token"] is not None
    assert len(data["accept_token"]) == 36  # UUID format


def test_draft_has_no_token(client: TestClient):
    ctx = _setup(client)
    r = client.get(f"/quotes/{ctx['quote_id']}")
    assert r.json()["accept_token"] is None


def test_send_twice_keeps_same_token(client: TestClient):
    ctx = _setup(client)
    t1 = _send(client, ctx["quote_id"])["accept_token"]
    r2 = client.post(f"/quotes/{ctx['quote_id']}/send")
    assert r2.status_code == 409
    assert client.get(f"/quotes/{ctx['quote_id']}").json()["accept_token"] == t1


# ── public by-token read ──────────────────────────────────────────────────────

def test_by_token_returns_quote_summary(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    r = client.get(f"/quotes/by-token/{token}")
    assert r.status_code == 200
    data = r.json()
    assert data["quote_number"].startswith("TIL-")
    assert data["title"] == "Tilbud på malerarbejde"
    assert data["status"] == "sent"
    assert data["total"] > 0
    assert "lines" in data
    assert len(data["lines"]) == 1


def test_by_token_includes_company_name(client: TestClient):
    # The company_name comes from the session company (created by conftest)
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    data = client.get(f"/quotes/by-token/{token}").json()
    # Company name should be "Test Firma AS" (from conftest company_id_fixture)
    assert data["company_name"] == "Test Firma AS"


def test_by_token_invalid_returns_404(client: TestClient):
    r = client.get("/quotes/by-token/nonexistent-token")
    assert r.status_code == 404


# ── accept ────────────────────────────────────────────────────────────────────

def test_accept_via_token(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    r = client.post(f"/quotes/by-token/{token}/accept")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "accepted"
    assert data["accepted_at"] is not None


def test_accept_transitions_project_to_active(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    client.post(f"/quotes/by-token/{token}/accept")
    proj = client.get(f"/projects/{ctx['project_id']}").json()
    assert proj["status"] == "active"


def test_accept_reflects_in_quote_get(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    client.post(f"/quotes/by-token/{token}/accept")
    data = client.get(f"/quotes/{ctx['quote_id']}").json()
    assert data["status"] == "accepted"
    assert data["accepted_at"] is not None


def test_accept_twice_returns_409(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    client.post(f"/quotes/by-token/{token}/accept")
    r = client.post(f"/quotes/by-token/{token}/accept")
    assert r.status_code == 409


def test_accept_invalid_token_returns_404(client: TestClient):
    r = client.post("/quotes/by-token/bad-token/accept")
    assert r.status_code == 404


# ── reject ────────────────────────────────────────────────────────────────────

def test_reject_via_token(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    r = client.post(f"/quotes/by-token/{token}/reject", json={"reason": "For dyrt"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "rejected"
    assert data["rejected_at"] is not None
    assert data["rejection_reason"] == "For dyrt"


def test_reject_without_reason(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    r = client.post(f"/quotes/by-token/{token}/reject", json={})
    assert r.status_code == 200
    assert r.json()["rejection_reason"] is None


def test_reject_twice_returns_409(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    client.post(f"/quotes/by-token/{token}/reject", json={})
    r = client.post(f"/quotes/by-token/{token}/reject", json={})
    assert r.status_code == 409


def test_cannot_accept_rejected_quote(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    client.post(f"/quotes/by-token/{token}/reject", json={})
    r = client.post(f"/quotes/by-token/{token}/accept")
    assert r.status_code == 409


def test_reject_invalid_token_returns_404(client: TestClient):
    r = client.post("/quotes/by-token/bad-token/reject", json={})
    assert r.status_code == 404


# ── draft cannot be accepted/rejected ────────────────────────────────────────

def test_draft_quote_has_no_accept_endpoint(client: TestClient):
    _setup(client)
    r = client.post("/quotes/by-token/no-token-yet/accept")
    assert r.status_code == 404


# ── dashboard win rate ────────────────────────────────────────────────────────

def test_dashboard_includes_quotes_accepted(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    client.post(f"/quotes/by-token/{token}/accept")
    dash = client.get("/dashboard").json()
    assert dash["quotes_accepted"] == 1


def test_dashboard_win_rate_is_100_when_one_accepted(client: TestClient):
    ctx = _setup(client)
    token = _send(client, ctx["quote_id"])["accept_token"]
    client.post(f"/quotes/by-token/{token}/accept")
    dash = client.get("/dashboard").json()
    assert dash["quotes_win_rate"] == 100.0


def test_dashboard_win_rate_50_when_one_accepted_one_rejected(client: TestClient):
    ctx = _setup(client)
    cust2 = client.post("/customers/", json={"name": "K2"}).json()
    proj2 = client.post("/projects/", json={
        "customer_id": cust2["id"], "title": "Sag 2", "status": "draft",
    }).json()
    q2 = client.post("/quotes/", json={
        "project_id": proj2["id"], "title": "Tilbud 2",
        "quote_type": "line",
        "lines": [{"description": "Loft", "unit": "m2", "quantity": 20, "unit_price": 100}],
    }).json()
    t1 = _send(client, ctx["quote_id"])["accept_token"]
    t2 = client.post(f"/quotes/{q2['id']}/send").json()["accept_token"]
    client.post(f"/quotes/by-token/{t1}/accept")
    client.post(f"/quotes/by-token/{t2}/reject", json={})
    dash = client.get("/dashboard").json()
    assert dash["quotes_win_rate"] == 50.0


def test_dashboard_win_rate_none_when_no_closed_quotes(client: TestClient):
    dash = client.get("/dashboard").json()
    assert dash["quotes_win_rate"] is None


# ── accept page accessible ────────────────────────────────────────────────────

def test_accept_page_returns_html(client: TestClient):
    r = client.get("/accept")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
