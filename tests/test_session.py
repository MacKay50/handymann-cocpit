"""
Tests for the session cookie mechanism.
POST /session/select-company sets a signed cookie.
GET  /session/current returns the active company.
DELETE /session/logout clears the cookie.
Any endpoint without a valid cookie returns 401.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

from haandvaerker.main import app
from haandvaerker.database import get_session


@pytest.fixture(name="plain_session")
def plain_session_fixture():
    """An in-memory session with no dependency overrides — used by session tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="plain_client")
def plain_client_fixture(plain_session: Session):
    """A client with only get_session overridden — no company_id override.
    This lets us test the real cookie-based auth path.
    """
    def override_get_session():
        yield plain_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(name="plain_company_id")
def plain_company_id_fixture(plain_client: TestClient) -> str:
    r = plain_client.post("/companies/", json={"name": "Session Test Firma"})
    assert r.status_code == 201
    return r.json()["id"]


# ── Test 1: POST /session/select-company sets a signed cookie ─────────────────

def test_select_company_sets_cookie(plain_client: TestClient, plain_company_id: str):
    """POST /session/select-company sets a signed cookie."""
    r = plain_client.post(
        "/session/select-company",
        json={"company_id": plain_company_id},
    )
    assert r.status_code == 200
    assert "haandvaerker_company" in r.cookies


# ── Test 2: GET /session/current returns active company after selection ────────

def test_get_current_returns_company(plain_client: TestClient, plain_company_id: str):
    """GET /session/current returns active company after selection."""
    plain_client.post(
        "/session/select-company",
        json={"company_id": plain_company_id},
    )
    r = plain_client.get("/session/current")
    assert r.status_code == 200
    data = r.json()
    assert data["company_id"] == plain_company_id
    assert "company_name" in data


# ── Test 3: Endpoint without cookie returns 401 ────────────────────────────────

def test_endpoint_without_cookie_returns_401(plain_client: TestClient):
    """Any endpoint guarded by get_company_context returns 401 without a cookie.
    We test /customers/ which after the sweep requires CompanyContextDep.
    """
    # Ensure no cookie is set
    plain_client.cookies.clear()
    r = plain_client.get("/customers/")
    assert r.status_code == 401
    assert "detail" in r.json()


# ── Test 4: POST /session/select-company with non-existent company returns 422 ─

def test_select_invalid_company_returns_422(plain_client: TestClient):
    """POST /session/select-company with non-existent company_id returns 422."""
    r = plain_client.post(
        "/session/select-company",
        json={"company_id": "does-not-exist"},
    )
    assert r.status_code == 422


# ── Test 5: DELETE /session/logout clears the cookie ─────────────────────────

def test_logout_clears_cookie(plain_client: TestClient, plain_company_id: str):
    """DELETE /session/logout clears the session cookie."""
    plain_client.post(
        "/session/select-company",
        json={"company_id": plain_company_id},
    )
    r = plain_client.delete("/session/logout")
    assert r.status_code == 200
    # After logout, /session/current should return 401
    r2 = plain_client.get("/session/current")
    assert r2.status_code == 401
