from __future__ import annotations

import io
import pathlib

from fastapi.testclient import TestClient


FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def test_import_economic_customers_success(client: TestClient, company_id: str) -> None:
    fp = str(FIXTURES_DIR / "economic_customers_sample.csv")
    r = client.post(f"/economic-customers/import?company_id={company_id}&file_path={fp}")
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["rows_imported"] == 3
    assert data["errors"] == []


def test_import_economic_customers_malformed_csv(client: TestClient, company_id: str) -> None:
    # CSV row with blank Navn (position 1) — parser raises "Navn må ikke være tomt"
    bad_csv = b"Kundenummer;Navn;Adresse;Postnummer;By;CVR;Email;Telefon\n9999;;Bredgade 1;1000;KBH;12345678;;\n"
    r = client.post(
        f"/economic-customers/import-upload?company_id={company_id}",
        files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
    )
    assert r.status_code == 422, r.json()


def test_import_economic_customers_duplicate(client: TestClient, company_id: str) -> None:
    fp = str(FIXTURES_DIR / "economic_customers_sample.csv")
    r1 = client.post(f"/economic-customers/import?company_id={company_id}&file_path={fp}")
    assert r1.status_code == 201, r1.json()

    r2 = client.post(f"/economic-customers/import?company_id={company_id}&file_path={fp}")
    assert r2.status_code == 409, r2.json()


def test_list_economic_customers(client: TestClient, company_id: str) -> None:
    fp = str(FIXTURES_DIR / "economic_customers_sample.csv")
    r_import = client.post(f"/economic-customers/import?company_id={company_id}&file_path={fp}")
    assert r_import.status_code == 201, r_import.json()

    r = client.get(f"/economic-customers/?company_id={company_id}")
    assert r.status_code == 200, r.json()
    items = r.json()
    assert len(items) >= 3
    # cvr_masked present (not cvr_number)
    for item in items:
        assert "cvr_number" not in item
        assert "cvr_masked" in item
