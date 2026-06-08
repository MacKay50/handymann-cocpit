"""Tests for GET /bank-transactions/ list endpoint."""
from __future__ import annotations

import pathlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fixtures_dir() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "fixtures"


def test_list_bank_transactions(client: TestClient, company_id: str, fixtures_dir: pathlib.Path) -> None:
    """All 5 rows importable and listable."""
    fp = str(fixtures_dir / "danske_bank_sample.csv")
    client.post(f"/bank-transactions/import?file_path={fp}")

    r = client.get("/bank-transactions/")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert len(data) == 5
    assert all("amount_ore" in item for item in data)
    assert all("is_credit" in item for item in data)


def test_list_bank_transactions_status_filter(client: TestClient, company_id: str, fixtures_dir: pathlib.Path) -> None:
    """Status filter returns only matching rows."""
    fp = str(fixtures_dir / "danske_bank_sample.csv")
    client.post(f"/bank-transactions/import?file_path={fp}")

    r = client.get("/bank-transactions/?status=unmatched")
    assert r.status_code == 200, r.json()
    assert all(item["status"] == "unmatched" for item in r.json())


def test_list_bank_transactions_active_only_default(client: TestClient, company_id: str, fixtures_dir: pathlib.Path) -> None:
    """active_only=True by default — active rows returned."""
    fp = str(fixtures_dir / "danske_bank_sample.csv")
    client.post(f"/bank-transactions/import?file_path={fp}")

    r = client.get("/bank-transactions/")
    assert r.status_code == 200
    assert all(item["active"] is True for item in r.json())


def test_list_bank_transactions_returns_session_company_only(
    client: TestClient, company_id: str, fixtures_dir: pathlib.Path
) -> None:
    """List is scoped to the session company."""
    fp = str(fixtures_dir / "danske_bank_sample.csv")
    client.post(f"/bank-transactions/import?file_path={fp}")

    r = client.get("/bank-transactions/")
    assert r.status_code == 200
    assert all(item["company_id"] == company_id for item in r.json())
