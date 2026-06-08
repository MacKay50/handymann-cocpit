from fastapi.testclient import TestClient


def _setup(client: TestClient) -> dict:
    cid = client.post("/customers/", json={"name": "Kunde"}).json()["id"]
    return {"customer_id": cid}


def _post_enquiry(client: TestClient, **extra) -> dict:
    payload = {
        "title": "Forespørgsel om malerarbejde",
        "source": "phone",
        **extra,
    }
    r = client.post("/enquiries/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse ---

def test_create_enquiry_minimal(client: TestClient, company_id: str):
    data = _post_enquiry(client)
    assert data["status"] == "new"
    assert data["active"] is True
    assert data["company_id"] == company_id
    assert data["project_id"] is None


def test_create_enquiry_with_contact(client: TestClient):
    data = _post_enquiry(
        client,
        contact_name="Lars Jensen",
        contact_phone="12345678",
        contact_email="lars@example.com",
    )
    assert data["contact_name"] == "Lars Jensen"
    assert data["contact_phone"] == "12345678"


def test_create_enquiry_with_known_customer(client: TestClient):
    ctx = _setup(client)
    data = _post_enquiry(client, customer_id=ctx["customer_id"])
    assert data["customer_id"] == ctx["customer_id"]


def test_duplicate_id_rejected(client: TestClient):
    _post_enquiry(client, **{"id": "fixed-enq"})
    r = client.post("/enquiries/", json={
        "id": "fixed-enq", "title": "Duplikat", "source": "email",
    })
    assert r.status_code == 409


# --- Opdatering ---

def test_update_new_enquiry(client: TestClient):
    enq = _post_enquiry(client)
    r = client.patch(f"/enquiries/{enq['id']}", json={
        "title": "Opdateret forespørgsel",
        "contact_phone": "87654321",
    })
    assert r.status_code == 200
    assert r.json()["title"] == "Opdateret forespørgsel"
    assert r.json()["contact_phone"] == "87654321"


def test_update_converted_enquiry_rejected(client: TestClient):
    ctx = _setup(client)
    enq = _post_enquiry(
        client,
        contact_name="Test Person",
        contact_phone="12345678",
        notes="Test opgavebeskrivelse",
        address="Testvej 1, 2000 Frederiksberg",
        work_type="Maling",
    )
    client.post(f"/enquiries/{enq['id']}/qualify")
    client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": ctx["customer_id"],
        "project_title": "Ny sag",
    })
    r = client.patch(f"/enquiries/{enq['id']}", json={"title": "Ny"})
    assert r.status_code == 409


def test_get_enquiry_not_found(client: TestClient):
    assert client.get("/enquiries/ukendt").status_code == 404


# --- Liste og filtrering ---

def test_list_enquiries(client: TestClient):
    _post_enquiry(client)
    _post_enquiry(client)
    assert len(client.get("/enquiries/").json()) == 2


def test_filter_by_status(client: TestClient):
    enq = _post_enquiry(client)
    _post_enquiry(client)
    client.post(f"/enquiries/{enq['id']}/qualify")
    r = client.get("/enquiries/?status=qualified")
    assert len(r.json()) == 1


def test_filter_by_source(client: TestClient):
    _post_enquiry(client, source="email")
    _post_enquiry(client, source="phone")
    r = client.get("/enquiries/?source=email")
    assert len(r.json()) == 1


# --- Status-overgange ---

def test_qualify_enquiry(client: TestClient):
    enq = _post_enquiry(client)
    r = client.post(f"/enquiries/{enq['id']}/qualify")
    assert r.status_code == 200
    assert r.json()["status"] == "qualified"


def test_close_from_new(client: TestClient):
    enq = _post_enquiry(client)
    r = client.post(f"/enquiries/{enq['id']}/close")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_close_from_qualified(client: TestClient):
    enq = _post_enquiry(client)
    client.post(f"/enquiries/{enq['id']}/qualify")
    r = client.post(f"/enquiries/{enq['id']}/close")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_invalid_transition_from_converted(client: TestClient):
    ctx = _setup(client)
    enq = _post_enquiry(
        client,
        contact_name="Test Person",
        contact_phone="12345678",
        notes="Test opgavebeskrivelse",
        address="Testvej 1, 2000 Frederiksberg",
        work_type="Maling",
    )
    client.post(f"/enquiries/{enq['id']}/qualify")
    client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": ctx["customer_id"], "project_title": "Sag",
    })
    r = client.post(f"/enquiries/{enq['id']}/close")
    assert r.status_code == 409


def test_invalid_transition_from_closed(client: TestClient):
    enq = _post_enquiry(client)
    client.post(f"/enquiries/{enq['id']}/close")
    r = client.post(f"/enquiries/{enq['id']}/qualify")
    assert r.status_code == 409


# --- Konvertering ---

def test_convert_creates_project(client: TestClient, company_id: str):
    ctx = _setup(client)
    enq = _post_enquiry(
        client,
        contact_name="Test Person",
        contact_phone="12345678",
        notes="Test opgavebeskrivelse",
        address="Testvej 1, 2000 Frederiksberg",
        work_type="Maling",
    )
    client.post(f"/enquiries/{enq['id']}/qualify")
    r = client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": ctx["customer_id"],
        "project_title": "Malerarbejde 2026",
    })
    assert r.status_code == 201
    project = r.json()
    assert project["company_id"] == company_id
    assert project["customer_id"] == ctx["customer_id"]
    assert project["title"] == "Malerarbejde 2026"
    assert project["status"] == "draft"


def test_convert_links_enquiry_to_project(client: TestClient):
    ctx = _setup(client)
    enq = _post_enquiry(
        client,
        contact_name="Test Person",
        contact_phone="12345678",
        notes="Test opgavebeskrivelse",
        address="Testvej 1, 2000 Frederiksberg",
        work_type="Maling",
    )
    client.post(f"/enquiries/{enq['id']}/qualify")
    project = client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": ctx["customer_id"], "project_title": "Sag",
    }).json()
    enq_data = client.get(f"/enquiries/{enq['id']}").json()
    assert enq_data["status"] == "converted"
    assert enq_data["project_id"] == project["id"]
    assert project["enquiry_id"] == enq["id"]


def test_convert_from_new_rejected(client: TestClient):
    ctx = _setup(client)
    enq = _post_enquiry(client)
    r = client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": ctx["customer_id"], "project_title": "Sag",
    })
    assert r.status_code == 409


def test_convert_unknown_customer_rejected(client: TestClient):
    # Enquiry must be fully qualified so the qualification gate passes
    # and customer validation is actually reached.
    enq = _post_enquiry(
        client,
        contact_name="Test Person",
        contact_phone="12345678",
        notes="Test opgavebeskrivelse",
        address="Testvej 1, 2000 Frederiksberg",
        work_type="Maling",
    )
    client.post(f"/enquiries/{enq['id']}/qualify")
    r = client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": "ukendt-kunde", "project_title": "Sag",
    })
    assert r.status_code == 422


def test_convert_already_converted_rejected(client: TestClient):
    ctx = _setup(client)
    enq = _post_enquiry(
        client,
        contact_name="Test Person",
        contact_phone="12345678",
        notes="Test opgavebeskrivelse",
        address="Testvej 1, 2000 Frederiksberg",
        work_type="Maling",
    )
    client.post(f"/enquiries/{enq['id']}/qualify")
    client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": ctx["customer_id"], "project_title": "Sag 1",
    })
    r = client.post(f"/enquiries/{enq['id']}/convert", json={
        "customer_id": ctx["customer_id"], "project_title": "Sag 2",
    })
    assert r.status_code == 409


# --- Slet (blød) ---

def test_deactivate_enquiry(client: TestClient):
    enq = _post_enquiry(client)
    assert client.delete(f"/enquiries/{enq['id']}").status_code == 204
    assert all(e["id"] != enq["id"] for e in client.get("/enquiries/").json())
    direct = client.get(f"/enquiries/{enq['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False
