import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.pool import StaticPool

from haandvaerker.main import app
from haandvaerker.database import get_session
from haandvaerker.dependencies import get_company_context, CompanyContext


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session, company_id: str):
    def override_get_session():
        yield session

    def override_get_company_context():
        return CompanyContext(session=session, company_id=company_id)

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_company_context] = override_get_company_context
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(name="company_id")
def company_id_fixture(session: Session) -> str:
    # Create the company directly in the session so it's available before
    # the client fixture sets up the override.
    from haandvaerker.models.company import Company
    import uuid
    company = Company(id=str(uuid.uuid4()), name="Test Firma AS")
    session.add(company)
    session.commit()
    session.refresh(company)
    return company.id
