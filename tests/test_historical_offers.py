from __future__ import annotations
import tempfile
from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    cid = client.post("/companies/", json={"name": "Test Firma"}).json()["id"]
    return {"company_id": cid}


def _txt_file(content: str = "Tilbud nr 2024-001\nMaling af villa 120 m2\nPris ex. moms: 15.000 kr\nAntal timer: 40 timer") -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


# ── import endpoint ──────────────────────────────────────────────────────────

def test_import_txt_file_returns_201(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    r = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path})
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["status"] == "needs_review"
    assert data["file_path"] == path


def test_import_creates_historical_offer(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    assert job["historical_offer_id"] is not None
    offer_r = client.get(f"/historical-offers/{job['historical_offer_id']}")
    assert offer_r.status_code == 200
    data = offer_r.json()
    assert data["extraction_status"] == "needs_review"


def test_import_extracts_price_and_area(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    offer = client.get(f"/historical-offers/{job['historical_offer_id']}").json()
    assert offer["price_ex_vat"] == 15000.0
    assert offer["area_m2"] == 120.0


def test_import_extracts_hours(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    offer = client.get(f"/historical-offers/{job['historical_offer_id']}").json()
    assert offer["estimated_hours"] == 40.0


def test_import_idempotent_same_file(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    j1 = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    j2 = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    assert j1["id"] == j2["id"]


def test_import_missing_file_returns_422(client: TestClient):
    ctx = _setup(client)
    r = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": "C:/nonexistent/file.txt"})
    assert r.status_code == 422


def test_import_job_list(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path})
    r = client.get("/historical-offers/jobs/")
    assert r.status_code == 200
    assert len(r.json()) >= 1


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_list_offers_empty(client: TestClient):
    r = client.get("/historical-offers/")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_offer_not_found(client: TestClient):
    r = client.get("/historical-offers/nonexistent")
    assert r.status_code == 404


def test_update_offer_fields(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    oid = job["historical_offer_id"]
    r = client.patch(f"/historical-offers/{oid}", json={"title": "Villa maling 2024", "year": 2024})
    assert r.status_code == 200
    assert r.json()["title"] == "Villa maling 2024"
    assert r.json()["year"] == 2024


def test_approve_offer(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    oid = job["historical_offer_id"]
    r = client.post(f"/historical-offers/{oid}/approve")
    assert r.status_code == 200
    assert r.json()["extraction_status"] == "approved"


def test_approve_twice_returns_409(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    oid = job["historical_offer_id"]
    client.post(f"/historical-offers/{oid}/approve")
    r = client.post(f"/historical-offers/{oid}/approve")
    assert r.status_code == 409


def test_price_per_m2_computed(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    oid = job["historical_offer_id"]
    offer = client.get(f"/historical-offers/{oid}").json()
    assert offer["price_per_m2"] == round(15000.0 / 120.0, 2)


def test_soft_delete_offer(client: TestClient):
    ctx = _setup(client)
    path = _txt_file()
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    oid = job["historical_offer_id"]
    r = client.delete(f"/historical-offers/{oid}")
    assert r.status_code == 204
    # Still retrievable but not in active list
    r2 = client.get("/historical-offers/")
    assert all(o["id"] != oid for o in r2.json())


def test_filter_by_job_type(client: TestClient):
    ctx = _setup(client)
    path = _txt_file("Maling af hus 50 m2 pris ex. moms: 8000 kr")
    job = client.post("/historical-offers/import", params={"company_id": ctx["company_id"], "file_path": path}).json()
    oid = job["historical_offer_id"]
    client.post(f"/historical-offers/{oid}/approve")
    r = client.get("/historical-offers/", params={"job_type": "maling"})
    assert any(o["id"] == oid for o in r.json())


# ── offer_search service unit tests ─────────────────────────────────────────

def test_extract_offer_fields_price():
    from haandvaerker.services.historical_offer_extractor import extract_offer_fields
    fields = extract_offer_fields("Pris ex. moms: 25.000 kr. Areal 80 m2")
    assert fields["price_ex_vat"] == 25000.0
    assert fields["area_m2"] == 80.0


def test_extract_offer_fields_offer_number():
    from haandvaerker.services.historical_offer_extractor import extract_offer_fields
    fields = extract_offer_fields("Tilbudsnr: TIL-2024-042\nMaling")
    assert fields["offer_number"] == "TIL-2024-042"


def test_extract_offer_fields_year():
    from haandvaerker.services.historical_offer_extractor import extract_offer_fields
    fields = extract_offer_fields("Tilbud fra 2023 for maling")
    assert fields["year"] == 2023


def test_extract_offer_fields_job_type_maling():
    from haandvaerker.services.historical_offer_extractor import extract_offer_fields
    fields = extract_offer_fields("Malerarbejde på villa")
    assert fields["job_type"] == "maling"
