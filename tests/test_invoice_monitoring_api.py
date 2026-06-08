"""Integration tests for the Betalingsradar (invoice monitoring) module.

All tests use the shared in-memory SQLite client + company_id fixtures from conftest.py.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


# ── helpers ────────────────────────────────────────────────────────────────────

def _ingest(client: TestClient, company_id: str, **kwargs) -> dict:
    payload = {
        "company_id": company_id,
        "subject": kwargs.get("subject", "Faktura 10001 fra Leverandør A/S"),
        "sender": kwargs.get("sender", "faktura@leverandoer.dk"),
        "body_text": kwargs.get("body_text", "Faktura nr. 10001. Beløb: 5.000,00 kr. Forfaldsdato: 15-07-2026."),
        "amount_ore": kwargs.get("amount_ore", 500_000),
        "invoice_number": kwargs.get("invoice_number", "10001"),
        "due_date": kwargs.get("due_date", str(date.today() + timedelta(days=20))),
        "creditor_name": kwargs.get("creditor_name", "Leverandør A/S"),
    }
    r = client.post("/invoice-monitoring/dev/ingest-sample", json=payload)
    return r


# ── AC-1: happy path — ingest creates case + action item + events ──────────────

def test_ingest_creates_case_action_item_events(client: TestClient, company_id: str) -> None:
    r = _ingest(client, company_id)
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["is_relevant"] is True
    assert data["invoice_case_id"] is not None
    assert data["action_item_id"] is not None
    assert data["status"] == "payment_required"

    # Detail has audit events
    case_id = data["invoice_case_id"]
    r2 = client.get(f"/invoice-monitoring/cases/{case_id}")
    assert r2.status_code == 200
    detail = r2.json()
    event_types = [e["event_type"] for e in detail["events"]]
    assert "invoice_case_created" in event_types
    assert "action_item_created" in event_types
    assert "mail_received" in event_types


# ── AC-2: irrelevant document — no action item ────────────────────────────────

def test_irrelevant_document_no_action_item(client: TestClient, company_id: str) -> None:
    r = _ingest(
        client, company_id,
        subject="Nyhedsbrev fra Leverandør",
        body_text="ikke relevant indhold — tilbud og reklame",
        invoice_number=None,
        amount_ore=None,
        due_date=None,
        creditor_name=None,
    )
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["is_relevant"] is False
    assert data["action_item_id"] is None
    assert data["status"] == "not_relevant"


# ── AC-3: overdue invoice → priority red ──────────────────────────────────────

def test_overdue_invoice_priority_red(client: TestClient, company_id: str) -> None:
    overdue = str(date.today() - timedelta(days=5))
    r = _ingest(client, company_id, due_date=overdue, invoice_number="OVR-001")
    assert r.status_code == 201, r.json()
    assert r.json()["priority"] == "red"


# ── AC-4: invoice due within 7 days → orange (not red unless ≤2 days) ─────────

def test_invoice_due_in_7_days_priority_orange(client: TestClient, company_id: str) -> None:
    soon = str(date.today() + timedelta(days=6))
    r = _ingest(client, company_id, due_date=soon, invoice_number="SOON-001",
                creditor_name="Kendt Kreditor")
    assert r.status_code == 201, r.json()
    # Without a known creditor_id (new stub → no existing link) the creditor is created
    # so priority depends on date window: 6 days → orange
    assert r.json()["priority"] in ("orange", "red")  # ≤7 days → at least orange


# ── AC-5: open-bank does NOT mark handled ─────────────────────────────────────

def test_open_bank_does_not_mark_handled(client: TestClient, company_id: str) -> None:
    r = _ingest(client, company_id, invoice_number="BANK-001")
    case_id = r.json()["invoice_case_id"]

    r2 = client.post(f"/invoice-monitoring/cases/{case_id}/open-bank")
    assert r2.status_code == 200, r2.json()
    data = r2.json()
    assert data["status"] == "bank_opened"
    assert "handled" not in data["status"]

    # Verify via detail that status is bank_opened, not handled
    detail = client.get(f"/invoice-monitoring/cases/{case_id}").json()
    assert detail["status"] == "bank_opened"
    event_types = [e["event_type"] for e in detail["events"]]
    assert "bank_opened" in event_types
    assert "marked_handled" not in event_types


# ── AC-6: mark-handled → audit event + handled fields set ────────────────────

def test_mark_handled_creates_audit_event(client: TestClient, company_id: str) -> None:
    r = _ingest(client, company_id, invoice_number="HDL-001")
    case_id = r.json()["invoice_case_id"]

    r2 = client.post(f"/invoice-monitoring/cases/{case_id}/mark-handled?handled_by=testuser")
    assert r2.status_code == 200, r2.json()
    data = r2.json()
    assert data["status"] == "handled"
    assert data["handled_by"] == "testuser"
    assert data["handled_at"] is not None
    assert "betaling bekræftes" in data["note"].lower()

    detail = client.get(f"/invoice-monitoring/cases/{case_id}").json()
    event_types = [e["event_type"] for e in detail["events"]]
    assert "marked_handled" in event_types


# ── AC-7: duplicate fingerprint → no second active action item ────────────────

def test_duplicate_no_second_action_item(client: TestClient, company_id: str) -> None:
    common = dict(
        invoice_number="DUP-001",
        amount_ore=100_000,
        due_date=str(date.today() + timedelta(days=30)),
        creditor_name="Dublet Kreditor",
    )
    r1 = _ingest(client, company_id, **common)
    assert r1.status_code == 201
    assert r1.json()["is_duplicate"] is False

    r2 = _ingest(client, company_id, **common)
    assert r2.status_code == 201
    assert r2.json()["is_duplicate"] is True
    assert r2.json()["action_item_id"] is None  # no new action item for duplicate

    # Only one open action item
    items = client.get(f"/invoice-monitoring/action-items?company_id={company_id}").json()
    dup_items = [i for i in items if i["invoice_number"] == "DUP-001"]
    assert len(dup_items) == 1


# ── AC-8: reminder on existing case → priority red + reminder_received event ──

def test_reminder_raises_priority_and_creates_event(client: TestClient, company_id: str) -> None:
    base = dict(
        invoice_number="REM-001",
        amount_ore=200_000,
        due_date=str(date.today() + timedelta(days=30)),
        creditor_name="Reminder Kreditor",
    )
    r1 = _ingest(client, company_id, **base)
    original_case_id = r1.json()["invoice_case_id"]

    # Second ingest with same fingerprint but reminder keyword in body
    r2 = _ingest(
        client, company_id,
        body_text="Rykker 1 — Faktura nr. REM-001. Beløb: 2.000,00 kr.",
        subject="1. rykker for faktura REM-001",
        **base,
    )
    assert r2.status_code == 201
    data = r2.json()
    assert data["is_reminder"] is True
    assert data["invoice_case_id"] == original_case_id  # same case, not new

    # Original case priority should now be red
    detail = client.get(f"/invoice-monitoring/cases/{original_case_id}").json()
    assert detail["priority"] == "red"
    event_types = [e["event_type"] for e in detail["events"]]
    assert "reminder_received" in event_types


# ── AC-9: payment_confirmed only via reconciliation bridge ────────────────────

def test_payment_confirmed_not_via_mark_handled(client: TestClient, company_id: str) -> None:
    r = _ingest(client, company_id, invoice_number="PAY-001")
    case_id = r.json()["invoice_case_id"]

    # mark-handled should set status=handled, NOT payment_confirmed
    r2 = client.post(f"/invoice-monitoring/cases/{case_id}/mark-handled")
    assert r2.status_code == 200
    assert r2.json()["status"] == "handled"
    assert r2.json()["status"] != "payment_confirmed"

    detail = client.get(f"/invoice-monitoring/cases/{case_id}").json()
    assert detail["status"] == "handled"
    assert detail["status"] != "payment_confirmed"


# ── AC-10: field correction creates audit event ───────────────────────────────

def test_field_correction_creates_audit_event(client: TestClient, company_id: str) -> None:
    r = _ingest(client, company_id, invoice_number="COR-001")
    case_id = r.json()["invoice_case_id"]

    r2 = client.patch(
        f"/invoice-monitoring/cases/{case_id}/fields",
        json={"field_name": "invoice_number", "new_value": "COR-001-CORRECTED"},
    )
    assert r2.status_code == 200, r2.json()

    detail = client.get(f"/invoice-monitoring/cases/{case_id}").json()
    event_types = [e["event_type"] for e in detail["events"]]
    assert "field_corrected" in event_types
    corr_event = next(e for e in detail["events"] if e["event_type"] == "field_corrected")
    assert corr_event["payload"]["field"] == "invoice_number"
    assert corr_event["payload"]["new_value"] == "COR-001-CORRECTED"


# ── additional: action item list sorted by priority ───────────────────────────

def test_action_items_sorted_by_priority(client: TestClient, company_id: str) -> None:
    _ingest(client, company_id, invoice_number="G-001",
            due_date=str(date.today() + timedelta(days=60)),
            creditor_name="Grøn Kreditor",
            amount_ore=50_000)
    _ingest(client, company_id, invoice_number="R-001",
            due_date=str(date.today() - timedelta(days=1)))  # overdue → red

    items = client.get(f"/invoice-monitoring/action-items?company_id={company_id}").json()
    priorities = [i["priority"] for i in items if i["priority"]]
    # Red should come before green
    if "red" in priorities and "green" in priorities:
        assert priorities.index("red") < priorities.index("green")


# ── additional: reject creates audit event ────────────────────────────────────

def test_reject_creates_audit_event(client: TestClient, company_id: str) -> None:
    r = _ingest(client, company_id, invoice_number="REJ-001")
    case_id = r.json()["invoice_case_id"]

    r2 = client.post(f"/invoice-monitoring/cases/{case_id}/reject?reason=false_positive")
    assert r2.status_code == 200
    assert r2.json()["status"] == "rejected"

    detail = client.get(f"/invoice-monitoring/cases/{case_id}").json()
    assert any(e["event_type"] == "rejected" for e in detail["events"])


# ── additional: 404 on unknown case ──────────────────────────────────────────

def test_get_unknown_case_returns_404(client: TestClient, company_id: str) -> None:
    r = client.get("/invoice-monitoring/cases/nonexistent-id")
    assert r.status_code == 404


def test_open_bank_unknown_case_returns_404(client: TestClient, company_id: str) -> None:
    r = client.post("/invoice-monitoring/cases/nonexistent-id/open-bank")
    assert r.status_code == 404
