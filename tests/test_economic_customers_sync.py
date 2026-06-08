from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from haandvaerker.models.customer import Customer
from haandvaerker.models.economic_customer import EconomicCustomer


def test_sync_all_creates_and_matches(client: TestClient, session: Session, company_id: str) -> None:
    # Arrange: one existing Customer with a known CVR
    existing_customer = Customer(
        company_id=company_id,
        name="Existing Kunde",
        cvr_number="87654321",
    )
    session.add(existing_customer)

    # ec1: CVR matches existing Customer → should be MATCHED
    ec1 = EconomicCustomer(
        company_id=company_id,
        economic_customer_number="1001",
        name="Existing Kunde",
        cvr_number="87654321",
    )
    # ec2: no matching Customer → should CREATE a new one
    ec2 = EconomicCustomer(
        company_id=company_id,
        economic_customer_number="1002",
        name="Ny Kunde",
        cvr_number="11223344",
    )
    session.add(ec1)
    session.add(ec2)
    session.commit()

    # Act
    r = client.post(f"/economic-customers/sync-all?company_id={company_id}")

    # Assert response shape
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data == {"matched": 1, "created": 1, "skipped": 0, "warnings": []}

    # Assert ec2 resulted in a new Customer with economic_customer_number populated
    session.expire_all()
    created = session.exec(
        select(Customer).where(Customer.cvr_number == "11223344")
    ).first()
    assert created is not None
    assert created.economic_customer_number == "1002"


def test_sync_single_new_customer_creates(client: TestClient, session: Session, company_id: str) -> None:
    ec = EconomicCustomer(
        company_id=company_id,
        economic_customer_number="5001",
        name="Ny Enkelt Kunde",
        cvr_number="77665544",
    )
    session.add(ec)
    session.commit()

    r = client.post(f"/economic-customers/{ec.id}/sync")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert "cvr_masked" in data
    assert data["name"] == "Ny Enkelt Kunde"

    # Verify the EconomicCustomer now has a linked_customer_id
    session.expire_all()
    ec_refreshed = session.get(EconomicCustomer, ec.id)
    assert ec_refreshed is not None
    assert ec_refreshed.linked_customer_id is not None


def test_sync_already_linked_returns_200(client: TestClient, session: Session, company_id: str) -> None:
    # Create a Customer and link an EconomicCustomer to it
    customer = Customer(
        company_id=company_id,
        name="Allerede Linket",
        cvr_number="55443322",
    )
    session.add(customer)

    ec = EconomicCustomer(
        company_id=company_id,
        economic_customer_number="2001",
        name="Allerede Linket",
        cvr_number="55443322",
        linked_customer_id=customer.id,
    )
    session.add(ec)
    session.commit()

    # Single sync should return 200 with the existing Customer
    r = client.post(f"/economic-customers/{ec.id}/sync")
    assert r.status_code == 200, r.json()
    data = r.json()
    # Must return CustomerRead which has cvr_masked, not cvr_number
    assert "cvr_masked" in data
    assert "cvr_number" not in data
    assert data["id"] == customer.id


def test_single_sync_blank_name_returns_422(client: TestClient, session: Session, company_id: str) -> None:
    ec = EconomicCustomer(
        company_id=company_id,
        economic_customer_number="3001",
        name="",
        cvr_number="12345678",
    )
    session.add(ec)
    session.commit()

    r = client.post(f"/economic-customers/{ec.id}/sync")
    assert r.status_code == 422, r.json()
    assert "tomt navn" in r.json()["detail"]


def test_sync_all_with_blank_name_skips_with_warning(
    client: TestClient, session: Session, company_id: str
) -> None:
    ec = EconomicCustomer(
        company_id=company_id,
        economic_customer_number="4001",
        name="",
        cvr_number="99887766",
    )
    session.add(ec)
    session.commit()

    r = client.post(f"/economic-customers/sync-all?company_id={company_id}")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["skipped"] == 1
    assert len(data["warnings"]) == 1
    assert "tomt navn" in data["warnings"][0]
