"""Tests for PATCH /economic-invoices/{id}/link-invoice and DAT-01 fix."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from haandvaerker.models.economic_invoice import EconomicInvoice, EconomicInvoiceStatus
from haandvaerker.models.invoice import Invoice, InvoiceStatus
from haandvaerker.models.project import Project, ProjectStatus


@pytest.fixture
def project(session: Session, company_id: str) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        company_id=company_id,
        customer_id=str(uuid.uuid4()),
        title="Testprojekt",
        status=ProjectStatus.active,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


@pytest.fixture
def invoice(session: Session, company_id: str, project: Project) -> Invoice:
    inv = Invoice(
        id=str(uuid.uuid4()),
        company_id=company_id,
        project_id=project.id,
        customer_id=project.customer_id,
        invoice_number="2025-0001",
        title="Testfaktura",
        issue_date=date(2025, 1, 1),
        due_date=date(2025, 1, 31),
        status=InvoiceStatus.sent,
        subtotal=1000.0,
        vat_amount=250.0,
        total=1250.0,
    )
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return inv


@pytest.fixture
def economic_invoice(session: Session, company_id: str) -> EconomicInvoice:
    ec = EconomicInvoice(
        id=str(uuid.uuid4()),
        company_id=company_id,
        economic_invoice_number="EC-001",
        customer_name="Test Kunde",
        net_amount_ore=100000,
        vat_amount_ore=25000,
        gross_amount_ore=125000,
        invoice_date=date(2025, 1, 1),
        due_date=date(2025, 1, 31),
        status=EconomicInvoiceStatus.unmatched,
    )
    session.add(ec)
    session.commit()
    session.refresh(ec)
    return ec


def test_link_invoice_sets_invoice_id(
    client: TestClient,
    economic_invoice: EconomicInvoice,
    invoice: Invoice,
) -> None:
    """PATCH with valid invoice_id sets the link and returns updated record."""
    r = client.patch(
        f"/economic-invoices/{economic_invoice.id}/link-invoice",
        json={"invoice_id": invoice.id},
    )
    assert r.status_code == 200, r.json()
    data = r.json()
    assert data["invoice_id"] == invoice.id
    assert data["id"] == economic_invoice.id


def test_link_invoice_clears_with_null(
    client: TestClient,
    session: Session,
    economic_invoice: EconomicInvoice,
    invoice: Invoice,
) -> None:
    """PATCH with invoice_id=null clears the link."""
    # First link it
    economic_invoice.invoice_id = invoice.id
    session.add(economic_invoice)
    session.commit()

    r = client.patch(
        f"/economic-invoices/{economic_invoice.id}/link-invoice",
        json={"invoice_id": None},
    )
    assert r.status_code == 200, r.json()
    assert r.json()["invoice_id"] is None


def test_link_invoice_wrong_company_returns_422(
    client: TestClient,
    session: Session,
    economic_invoice: EconomicInvoice,
) -> None:
    """invoice_id from a different company returns 422."""
    from haandvaerker.models.company import Company

    other_company = Company(id=str(uuid.uuid4()), name="Andet Firma")
    session.add(other_company)
    session.commit()

    other_project = Project(
        id=str(uuid.uuid4()),
        company_id=other_company.id,
        customer_id=str(uuid.uuid4()),
        title="Andet projekt",
        status=ProjectStatus.active,
    )
    session.add(other_project)
    session.commit()

    other_invoice = Invoice(
        id=str(uuid.uuid4()),
        company_id=other_company.id,
        project_id=other_project.id,
        customer_id=other_project.customer_id,
        invoice_number="2025-9999",
        title="Anden faktura",
        issue_date=date(2025, 1, 1),
        due_date=date(2025, 1, 31),
        status=InvoiceStatus.draft,
        subtotal=500.0,
        vat_amount=125.0,
        total=625.0,
    )
    session.add(other_invoice)
    session.commit()

    r = client.patch(
        f"/economic-invoices/{economic_invoice.id}/link-invoice",
        json={"invoice_id": other_invoice.id},
    )
    assert r.status_code == 422, r.json()


def test_link_invoice_nonexistent_invoice_returns_404(
    client: TestClient,
    economic_invoice: EconomicInvoice,
) -> None:
    """invoice_id that doesn't exist returns 404."""
    r = client.patch(
        f"/economic-invoices/{economic_invoice.id}/link-invoice",
        json={"invoice_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404, r.json()


def test_get_economic_invoice_exposes_invoice_id(
    client: TestClient,
    session: Session,
    economic_invoice: EconomicInvoice,
    invoice: Invoice,
) -> None:
    """GET /economic-invoices/ includes invoice_id field in response (DAT-01 fix)."""
    # Set invoice_id directly in DB
    economic_invoice.invoice_id = invoice.id
    session.add(economic_invoice)
    session.commit()

    r = client.get("/economic-invoices/")
    assert r.status_code == 200, r.json()
    data = r.json()
    assert len(data) >= 1
    matching = [item for item in data if item["id"] == economic_invoice.id]
    assert len(matching) == 1
    assert matching[0]["invoice_id"] == invoice.id
