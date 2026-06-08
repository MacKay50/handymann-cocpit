from fastapi.testclient import TestClient


def _post_message(client: TestClient, **extra) -> dict:
    payload = {
        "source": "email",
        "received_at": "2026-05-20T09:00:00",
        "sender_name": "Lars Jensen",
        "sender_email": "lars@example.com",
        "subject": "Forespørgsel om malerarbejde",
        "body": "Hej, vi søger en maler til vores hus...",
        **extra,
    }
    r = client.post("/inbox/", json=payload)
    assert r.status_code == 201, r.json()
    return r.json()


# --- Oprettelse ---

def test_create_message_minimal(client: TestClient, company_id: str):
    data = _post_message(client)
    assert data["status"] == "unread"
    assert data["active"] is True
    assert data["company_id"] == company_id
    assert data["enquiry_id"] is None


def test_create_message_phone(client: TestClient):
    data = _post_message(client, source="phone", sender_phone="12345678")
    assert data["source"] == "phone"
    assert data["sender_phone"] == "12345678"


def test_create_message_no_sender_info(client: TestClient):
    data = _post_message(client, sender_name=None, sender_email=None, subject=None, body=None)
    assert data["status"] == "unread"


def test_duplicate_id_rejected(client: TestClient):
    _post_message(client, **{"id": "fixed-msg"})
    r = client.post("/inbox/", json={
        "id": "fixed-msg", "source": "email",
        "received_at": "2026-05-20T09:00:00",
    })
    assert r.status_code == 409


# --- Liste og filtrering ---

def test_list_messages(client: TestClient):
    _post_message(client)
    _post_message(client, source="phone")
    assert len(client.get("/inbox/").json()) == 2


def test_filter_returns_session_company_only(client: TestClient, company_id: str):
    _post_message(client)
    r = client.get("/inbox/")
    assert len(r.json()) == 1
    assert r.json()[0]["company_id"] == company_id


def test_filter_by_status(client: TestClient):
    msg = _post_message(client)
    _post_message(client)
    client.post(f"/inbox/{msg['id']}/read")
    r = client.get("/inbox/?status=read")
    assert len(r.json()) == 1


def test_filter_by_source(client: TestClient):
    _post_message(client, source="email")
    _post_message(client, source="phone")
    r = client.get("/inbox/?source=email")
    assert len(r.json()) == 1


def test_get_not_found(client: TestClient):
    assert client.get("/inbox/ukendt").status_code == 404


# --- Status-overgange ---

def test_mark_as_read(client: TestClient):
    msg = _post_message(client)
    r = client.post(f"/inbox/{msg['id']}/read")
    assert r.status_code == 200
    assert r.json()["status"] == "read"


def test_mark_as_read_idempotent(client: TestClient):
    msg = _post_message(client)
    client.post(f"/inbox/{msg['id']}/read")
    r = client.post(f"/inbox/{msg['id']}/read")
    assert r.status_code == 200
    assert r.json()["status"] == "read"


def test_archive_from_unread(client: TestClient):
    msg = _post_message(client)
    r = client.post(f"/inbox/{msg['id']}/archive")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_archive_from_read(client: TestClient):
    msg = _post_message(client)
    client.post(f"/inbox/{msg['id']}/read")
    r = client.post(f"/inbox/{msg['id']}/archive")
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_unread_from_archived(client: TestClient):
    msg = _post_message(client)
    client.post(f"/inbox/{msg['id']}/archive")
    r = client.post(f"/inbox/{msg['id']}/unread")
    assert r.status_code == 200
    assert r.json()["status"] == "unread"


def test_invalid_transition_from_converted(client: TestClient):
    msg = _post_message(client)
    client.post(f"/inbox/{msg['id']}/convert", json={
        "title": "Malerforespørgsel", "source": "email",
    })
    r = client.post(f"/inbox/{msg['id']}/archive")
    assert r.status_code == 409


# --- Konvertering til Enquiry ---

def test_convert_creates_enquiry(client: TestClient, company_id: str):
    msg = _post_message(client)
    r = client.post(f"/inbox/{msg['id']}/convert", json={
        "title": "Malerforespørgsel",
        "source": "email",
    })
    assert r.status_code == 201
    enquiry = r.json()
    assert enquiry["company_id"] == company_id
    assert enquiry["title"] == "Malerforespørgsel"
    assert enquiry["status"] == "new"
    assert enquiry["contact_name"] == msg["sender_name"]
    assert enquiry["contact_email"] == msg["sender_email"]


def test_convert_links_message_to_enquiry(client: TestClient):
    msg = _post_message(client)
    enquiry = client.post(f"/inbox/{msg['id']}/convert", json={
        "title": "Forespørgsel", "source": "email",
    }).json()
    msg_data = client.get(f"/inbox/{msg['id']}").json()
    assert msg_data["status"] == "converted"
    assert msg_data["enquiry_id"] == enquiry["id"]


def test_convert_already_converted_rejected(client: TestClient):
    msg = _post_message(client)
    client.post(f"/inbox/{msg['id']}/convert", json={"title": "Forespørgsel", "source": "email"})
    r = client.post(f"/inbox/{msg['id']}/convert", json={"title": "Duplikat", "source": "email"})
    assert r.status_code == 409


def test_convert_populates_contact_from_message(client: TestClient):
    msg = _post_message(client, sender_phone="87654321")
    enquiry = client.post(f"/inbox/{msg['id']}/convert", json={
        "title": "T", "source": "phone",
    }).json()
    assert enquiry["contact_phone"] == "87654321"


# --- Soft-delete ---

def test_deactivate_message(client: TestClient):
    msg = _post_message(client)
    assert client.delete(f"/inbox/{msg['id']}").status_code == 204
    assert all(m["id"] != msg["id"] for m in client.get("/inbox/").json())
    direct = client.get(f"/inbox/{msg['id']}")
    assert direct.status_code == 200
    assert direct.json()["active"] is False
