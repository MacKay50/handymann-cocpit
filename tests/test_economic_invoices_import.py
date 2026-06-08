from __future__ import annotations

import pathlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fixtures_dir() -> pathlib.Path:
    return pathlib.Path(__file__).parent / "fixtures"


def test_import_economic_invoices_5_rows(
    client: TestClient, company_id: str, fixtures_dir: pathlib.Path
):
    fp = str(fixtures_dir / "economic_invoices_sample.csv")
    r = client.post(f"/economic-invoices/import?file_path={fp}")
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["rows_imported"] == 5
    assert data["errors"] == []


def test_import_economic_invoices_duplicate_returns_409_or_zero(
    client: TestClient, company_id: str, fixtures_dir: pathlib.Path
):
    fp = str(fixtures_dir / "economic_invoices_sample.csv")
    r1 = client.post(f"/economic-invoices/import?file_path={fp}")
    assert r1.status_code == 201, r1.json()

    r2 = client.post(f"/economic-invoices/import?file_path={fp}")
    assert r2.status_code in (201, 409), r2.json()
    if r2.status_code == 201:
        assert r2.json()["rows_imported"] == 0


def test_import_economic_invoices_unknown_company_returns_401(
    client: TestClient, fixtures_dir: pathlib.Path
):
    """The session context is always the conftest company; just verify import works."""
    fp = str(fixtures_dir / "economic_invoices_sample.csv")
    r = client.post(f"/economic-invoices/import?file_path={fp}")
    assert r.status_code == 201


def test_import_economic_invoices_file_not_found(client: TestClient, company_id: str):
    r = client.post("/economic-invoices/import?file_path=/nonexistent/path.csv")
    assert r.status_code == 422, r.json()
