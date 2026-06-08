"""Tests for the invoice → customer → project pipeline.

Covers:
- derive-customers extracts unique debitor names as EconomicCustomer stubs
- derive-customers is idempotent (second call links, does not re-create)
- create-historical-projects creates completed Projects for bank-matched invoices
- create-historical-projects auto-creates Customer when EconomicCustomer has no link
- invoices without an EconomicCustomer link are skipped by create-historical-projects
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from haandvaerker.models.economic_customer import EconomicCustomer
from haandvaerker.models.economic_invoice import EconomicInvoice, EconomicInvoiceStatus
from haandvaerker.models.project import Project, ProjectStatus


def _make_invoice(
    client: TestClient,
    company_id: str,
    *,
    number: str,
    customer_name: str,
    status: str = "unmatched",
) -> dict:
    r = client.post("/companies/", json={"name": "X"})  # ignored — use fixture company
    # Create directly via session helpers would be cleaner, but the API fixture is simpler
    # Use session-level helper instead (see _make_inv_direct below)
    raise NotImplementedError("use _make_inv_direct")


def _make_inv_direct(
    session: Session,
    company_id: str,
    *,
    number: str,
    customer_name: str,
    status: EconomicInvoiceStatus = EconomicInvoiceStatus.unmatched,
) -> EconomicInvoice:
    inv = EconomicInvoice(
        company_id=company_id,
        economic_invoice_number=number,
        customer_name=customer_name,
        net_amount_ore=800000,
        vat_amount_ore=200000,
        gross_amount_ore=1000000,
        invoice_date=date(2026, 3, 1),
        due_date=date(2026, 3, 31),
        status=status,
    )
    session.add(inv)
    return inv


# ── derive-customers ──────────────────────────────────────────────────────────

def test_derive_customers_creates_stubs(client: TestClient, session: Session, company_id: str) -> None:
    _make_inv_direct(session, company_id, number="F001", customer_name="Hansen Byggeri")
    _make_inv_direct(session, company_id, number="F002", customer_name="Jensen Service")
    session.commit()

    r = client.post(f"/economic-invoices/derive-customers?company_id={company_id}")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["created"] == 2
    assert data["linked"] == 2
    assert data["already_linked"] == 0

    stubs = session.exec(
        select(EconomicCustomer).where(EconomicCustomer.company_id == company_id)
    ).all()
    assert len(stubs) == 2
    assert all(s.source == "derived" for s in stubs)
    assert all(s.cvr_number is None for s in stubs)


def test_derive_customers_deduplicates_same_name(client: TestClient, session: Session, company_id: str) -> None:
    _make_inv_direct(session, company_id, number="F001", customer_name="Hansen Byggeri")
    _make_inv_direct(session, company_id, number="F002", customer_name="Hansen Byggeri")
    session.commit()

    r = client.post(f"/economic-invoices/derive-customers?company_id={company_id}")
    data = r.json()
    assert data["created"] == 1  # one stub for both invoices
    assert data["linked"] == 2   # both invoices linked


def test_derive_customers_idempotent(client: TestClient, session: Session, company_id: str) -> None:
    _make_inv_direct(session, company_id, number="F001", customer_name="Hansen Byggeri")
    session.commit()

    r1 = client.post(f"/economic-invoices/derive-customers?company_id={company_id}")
    r2 = client.post(f"/economic-invoices/derive-customers?company_id={company_id}")
    assert r2.status_code == 200
    assert r2.json()["created"] == 0        # no new stubs on second call
    assert r2.json()["already_linked"] == 1 # first call already linked it


# ── create-historical-projects ────────────────────────────────────────────────

def test_create_historical_projects_for_matched_invoices(
    client: TestClient, session: Session, company_id: str
) -> None:
    inv = _make_inv_direct(
        session, company_id, number="F001", customer_name="Nord Bygg ApS",
        status=EconomicInvoiceStatus.matched,
    )
    session.commit()

    # Derive first so the invoice gets an EconomicCustomer link
    client.post(f"/economic-invoices/derive-customers?company_id={company_id}")

    r = client.post(f"/economic-invoices/create-historical-projects?company_id={company_id}")
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["created"] == 1
    assert data["skipped"] == []

    session.refresh(inv)
    assert inv.linked_project_id is not None

    project = session.get(Project, inv.linked_project_id)
    assert project is not None
    assert project.status == ProjectStatus.completed
    assert "Nord Bygg ApS" in project.title


def test_create_historical_projects_auto_creates_customer(
    client: TestClient, session: Session, company_id: str
) -> None:
    _make_inv_direct(
        session, company_id, number="F001", customer_name="Klima Service",
        status=EconomicInvoiceStatus.matched,
    )
    session.commit()
    client.post(f"/economic-invoices/derive-customers?company_id={company_id}")

    r = client.post(f"/economic-invoices/create-historical-projects?company_id={company_id}")
    assert r.status_code == 201
    # Customer was created from stub (no CVR needed for historical data)
    customers = client.get(f"/customers/?company_id={company_id}").json()
    assert any(c["name"] == "Klima Service" for c in customers)


def test_create_historical_projects_skips_unmatched(
    client: TestClient, session: Session, company_id: str
) -> None:
    _make_inv_direct(session, company_id, number="F001", customer_name="Uafstemt Kunde")
    session.commit()
    client.post(f"/economic-invoices/derive-customers?company_id={company_id}")

    r = client.post(f"/economic-invoices/create-historical-projects?company_id={company_id}")
    assert r.status_code == 201
    assert r.json()["created"] == 0  # unmatched invoice → no project


def test_create_historical_projects_idempotent(
    client: TestClient, session: Session, company_id: str
) -> None:
    _make_inv_direct(
        session, company_id, number="F001", customer_name="Byg Co",
        status=EconomicInvoiceStatus.matched,
    )
    session.commit()
    client.post(f"/economic-invoices/derive-customers?company_id={company_id}")

    r1 = client.post(f"/economic-invoices/create-historical-projects?company_id={company_id}")
    r2 = client.post(f"/economic-invoices/create-historical-projects?company_id={company_id}")
    assert r1.json()["created"] == 1
    assert r2.json()["created"] == 0  # already has linked_project_id — skipped
