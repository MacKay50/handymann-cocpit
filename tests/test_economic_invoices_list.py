"""Tests for GET /economic-invoices/ list endpoint."""
from __future__ import annotations

import pathlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fixtures_dir() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "fixtures"


def test_list_economic_invoices(client: TestClient, company_id: str, fixtures_dir: pathlib.Path) -> None:
    """All 5 rows importable and listable."""
    fp = str(fixtures_dir / "economic_invoices_sample.csv")
    client.post(f"/economic-invoices/import?file_path={fp}")

    r = client.get("/economic-invoices/")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert len(data) == 5
    assert all("is_overdue" in item for item in data)
    assert all("gross_amount_ore" in item for item in data)


def test_list_economic_invoices_overdue_computed(client: TestClient, company_id: str, fixtures_dir: pathlib.Path) -> None:
    """is_overdue computed at read time."""
    fp = str(fixtures_dir / "economic_invoices_sample.csv")
    client.post(f"/economic-invoices/import?file_path={fp}")

    r = client.get("/economic-invoices/")
    assert r.status_code == 200
    data = r.json()

    unmatched_past = [i for i in data if i["status"] == "unmatched"]
    assert len(unmatched_past) > 0
    assert all(i["is_overdue"] is True for i in unmatched_past)


def test_is_overdue_clears_after_match(client: TestClient, company_id: str, fixtures_dir: pathlib.Path) -> None:
    """is_overdue=False once an invoice is matched."""
    bank_fp = str(fixtures_dir / "danske_bank_sample.csv")
    inv_fp = str(fixtures_dir / "economic_invoices_sample.csv")
    client.post(f"/bank-transactions/import?file_path={bank_fp}")
    client.post(f"/economic-invoices/import?file_path={inv_fp}")

    before = client.get("/economic-invoices/").json()
    assert any(i["is_overdue"] for i in before)

    r = client.post("/reconciliation/match")
    assert r.status_code == 201
    assert r.json()["deterministic_count"] > 0

    after = client.get("/economic-invoices/?status=matched").json()
    assert len(after) > 0
    assert all(i["is_overdue"] is False for i in after)


def test_list_economic_invoices_status_filter(client: TestClient, company_id: str, fixtures_dir: pathlib.Path) -> None:
    """Status filter returns only matching rows."""
    fp = str(fixtures_dir / "economic_invoices_sample.csv")
    client.post(f"/economic-invoices/import?file_path={fp}")

    r = client.get("/economic-invoices/?status=unmatched")
    assert r.status_code == 200
    assert all(item["status"] == "unmatched" for item in r.json())


def test_list_economic_invoices_scoped_to_session_company(
    client: TestClient, company_id: str, fixtures_dir: pathlib.Path
) -> None:
    """All returned rows belong to the session company."""
    fp = str(fixtures_dir / "economic_invoices_sample.csv")
    client.post(f"/economic-invoices/import?file_path={fp}")

    r = client.get("/economic-invoices/")
    assert r.status_code == 200
    assert all(item["company_id"] == company_id for item in r.json())
