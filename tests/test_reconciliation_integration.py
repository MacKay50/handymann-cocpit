"""End-to-end reconciliation integration test.

Covers the full accountant workflow: import → match → view → manual-match → reject → verify.
Uses conftest.py fixtures (client, company_id) via pytest autodiscovery.
"""
from __future__ import annotations

import pathlib
from fastapi.testclient import TestClient

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_full_reconciliation_workflow(client: TestClient, company_id: str) -> None:
    """
    Scenario:
      - 3 bank transactions: TX-A (500000 øre), TX-B (300000 øre), TX-C (150000 øre)
      - 3 e-conomic invoices: INV-001 (gross 500000), INV-002 (gross 300000), INV-003 (gross 1000000)
      - Deterministic matcher creates 2 auto-confirmed matches (A→001, B→002).
      - INV-003 and TX-C remain unmatched (amount mismatch).
      - Manual-match links TX-C → INV-003.
      - Reject the A→001 match.
      - Verify final state across both list endpoints.
    """
    bank_fp = str(_FIXTURES / "integration_bank.csv")
    inv_fp = str(_FIXTURES / "integration_invoices.csv")

    # ── 1. Import data ────────────────────────────────────────────────────────
    r_bank = client.post(
        f"/bank-transactions/import?company_id={company_id}&file_path={bank_fp}"
    )
    assert r_bank.status_code == 201, r_bank.json()
    assert r_bank.json()["rows_imported"] == 3

    r_inv = client.post(
        f"/economic-invoices/import?company_id={company_id}&file_path={inv_fp}"
    )
    assert r_inv.status_code == 201, r_inv.json()
    assert r_inv.json()["rows_imported"] == 3

    # ── 2. Run deterministic matching ─────────────────────────────────────────
    r_match = client.post(f"/reconciliation/match?company_id={company_id}")
    assert r_match.status_code == 201, r_match.json()
    match_result = r_match.json()
    assert match_result["deterministic_count"] == 2

    # ── 3. Verify reconciliation view ─────────────────────────────────────────
    r_view = client.get(f"/reconciliation/?company_id={company_id}")
    assert r_view.status_code == 200, r_view.json()
    view = r_view.json()
    items = view["items"]
    orphans = view["orphan_transactions"]

    assert len(items) == 3
    matched_items = [i for i in items if i["reconciliation_status"] == "matched"]
    assert len(matched_items) == 2, "Expected 2 auto-confirmed matched invoices"

    unmatched_items = [i for i in items if i["reconciliation_status"] in ("unmatched", "overdue")]
    assert len(unmatched_items) == 1, "Expected 1 unmatched invoice (INV-003)"
    orphan_inv = unmatched_items[0]["economic_invoice"]
    assert orphan_inv["economic_invoice_number"] == "INT-003"

    assert len(orphans) == 1, "Expected 1 orphan bank transaction (TX-C)"
    orphan_tx = orphans[0]
    assert orphan_tx["amount_ore"] == 150000

    # ── 4. Manual-match orphan pair (TX-C → INV-003) ─────────────────────────
    orphan_inv_id = orphan_inv["id"]
    orphan_tx_id = orphan_tx["id"]

    r_manual = client.post(
        "/reconciliation/manual-match",
        json={"bank_transaction_id": orphan_tx_id, "economic_invoice_id": orphan_inv_id},
    )
    assert r_manual.status_code == 201, r_manual.json()
    manual_match = r_manual.json()
    assert manual_match["match_type"] == "manual"
    assert manual_match["confirmed"] is True

    # ── 5. Reject one of the auto-confirmed matches (A→INV-001) ──────────────
    # Find the INV-001 match ID from the view
    inv001_item = next(i for i in items if i["economic_invoice"]["economic_invoice_number"] == "INT-001")
    assert inv001_item["match"] is not None
    match_to_reject_id = inv001_item["match"]["id"]

    r_reject = client.post(f"/reconciliation/{match_to_reject_id}/reject")
    assert r_reject.status_code == 200, r_reject.json()
    rejected = r_reject.json()
    assert rejected["active"] is False

    # ── 6. Verify final state of economic invoices ───────────────────────────
    r_ei = client.get(f"/economic-invoices/?company_id={company_id}")
    assert r_ei.status_code == 200
    ei_data = {inv["economic_invoice_number"]: inv for inv in r_ei.json()}

    # INT-001: rejected → unmatched; due_date 01-04-2026 < today → overdue
    assert ei_data["INT-001"]["status"] == "unmatched"
    assert ei_data["INT-001"]["is_overdue"] is True

    # INT-002: still auto-matched → matched; is_overdue must be False
    assert ei_data["INT-002"]["status"] == "matched"
    assert ei_data["INT-002"]["is_overdue"] is False

    # INT-003: manual-matched → matched; is_overdue must be False
    assert ei_data["INT-003"]["status"] == "matched"
    assert ei_data["INT-003"]["is_overdue"] is False

    # ── 7. Verify final state of bank transactions ───────────────────────────
    r_bt = client.get(f"/bank-transactions/?company_id={company_id}")
    assert r_bt.status_code == 200
    bt_by_amount = {tx["amount_ore"]: tx for tx in r_bt.json()}

    # TX-A (500000): rejected → unmatched
    assert bt_by_amount[500000]["status"] == "unmatched"

    # TX-B (300000): still matched
    assert bt_by_amount[300000]["status"] == "matched"

    # TX-C (150000): manual-matched → matched
    assert bt_by_amount[150000]["status"] == "matched"
