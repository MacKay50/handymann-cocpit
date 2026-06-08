"""Tests for GET /enquiries/{id}/qualification-status and the convert gate (Phase 3)."""
from fastapi.testclient import TestClient


def _make_customer(client: TestClient) -> str:
    return client.post("/customers/", json={"name": "Kvalifikation Kunde"}).json()["id"]


def _post_enquiry(client: TestClient, **extra) -> dict:
    payload = {"title": "Forespørgsel om maling", "source": "phone", **extra}
    r = client.post("/enquiries/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


def _full_enquiry(client: TestClient) -> dict:
    return _post_enquiry(
        client,
        contact_name="Test Person",
        contact_phone="12345678",
        notes="Opgavebeskrivelse",
        address="Testvej 1, 2000 Frederiksberg",
        work_type="Maling",
    )


# --- qualification-status ---

def test_qualification_status_not_ready_when_empty(client: TestClient):
    enq = _post_enquiry(client)
    r = client.get(f"/enquiries/{enq['id']}/qualification-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    assert isinstance(body["checklist"], list)
    assert len(body["checklist"]) == 5
    assert isinstance(body["missing_fields"], list)
    assert len(body["missing_fields"]) > 0


def test_qualification_status_ready_when_all_fields_present(client: TestClient):
    enq = _full_enquiry(client)
    r = client.get(f"/enquiries/{enq['id']}/qualification-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True
    assert body["missing_fields"] == []
    assert all(gate["passed"] for gate in body["checklist"])


def test_qualification_status_contact_email_satisfies_contact_gate(client: TestClient):
    """contact_email (no phone) should satisfy the contact gate."""
    enq = _post_enquiry(
        client,
        contact_name="Person",
        contact_email="person@example.com",
        notes="Beskrivelse",
        address="Adressevej 2",
        work_type="Tømrer",
    )
    r = client.get(f"/enquiries/{enq['id']}/qualification-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is True


def test_qualification_status_missing_contact_info(client: TestClient):
    enq = _post_enquiry(
        client,
        contact_name="Person",
        notes="Beskrivelse",
        address="Adressevej 2",
        work_type="Tømrer",
        # no contact_email, no contact_phone
    )
    r = client.get(f"/enquiries/{enq['id']}/qualification-status")
    assert r.status_code == 200
    body = r.json()
    assert body["ready"] is False
    assert "contact_email_or_phone" in body["missing_fields"]


def test_qualification_status_not_found(client: TestClient):
    r = client.get("/enquiries/ukendt/qualification-status")
    assert r.status_code == 404


def test_qualification_status_checklist_has_5_gates(client: TestClient):
    enq = _post_enquiry(client)
    body = client.get(f"/enquiries/{enq['id']}/qualification-status").json()
    assert len(body["checklist"]) == 5


# --- convert gate ---

def test_convert_blocked_when_not_qualified(client: TestClient):
    cid = _make_customer(client)
    enq = _post_enquiry(client)  # no qualification fields
    client.post(f"/enquiries/{enq['id']}/qualify")
    r = client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": cid,
        "project_title": "Sag",
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "kvalificeret" in detail.lower() or "manglende" in detail.lower()


def test_convert_succeeds_when_qualified(client: TestClient):
    cid = _make_customer(client)
    enq = _full_enquiry(client)
    client.post(f"/enquiries/{enq['id']}/qualify")
    r = client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": cid,
        "project_title": "Maleropgave",
    })
    assert r.status_code == 201
    project = r.json()
    assert project["title"] == "Maleropgave"
    assert project["customer_id"] == cid


def test_convert_missing_fields_listed_in_error(client: TestClient):
    cid = _make_customer(client)
    enq = _post_enquiry(client, contact_name="Person", contact_phone="12345678")
    # notes, address, work_type missing
    client.post(f"/enquiries/{enq['id']}/qualify")
    r = client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": cid,
        "project_title": "Sag",
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    # At least one of the missing field names must appear in the error
    assert any(f in detail for f in ("notes", "address", "work_type"))
