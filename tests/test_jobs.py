"""Tests for POST /jobs/run-reminders."""
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from haandvaerker.config import REMINDER_FEE_ORE_2, REMINDER_FEE_ORE_3
from haandvaerker.models.customer import Customer
from haandvaerker.models.invoice import Invoice, InvoiceStatus
from haandvaerker.models.invoice_reminder import InvoiceReminder
from haandvaerker.models.project import Project


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_invoice(
    session: Session,
    company_id: str,
    days_overdue: int,
    status: InvoiceStatus = InvoiceStatus.sent,
) -> Invoice:
    """Create a customer + project + invoice overdue by `days_overdue` days."""
    import uuid

    customer = Customer(
        id=str(uuid.uuid4()),
        company_id=company_id,
        name="Test Kunde",
        email="kunde@example.com",
    )
    session.add(customer)

    project = Project(
        id=str(uuid.uuid4()),
        company_id=company_id,
        customer_id=customer.id,
        title="Test Projekt",
    )
    session.add(project)

    today = date.today()
    invoice = Invoice(
        id=str(uuid.uuid4()),
        company_id=company_id,
        project_id=project.id,
        customer_id=customer.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6].upper()}",
        title="Test Faktura",
        issue_date=today - timedelta(days=days_overdue + 30),
        due_date=today - timedelta(days=days_overdue),
        status=status,
        subtotal=1000.0,
        vat_amount=250.0,
        total=1250.0,
        active=True,
    )
    session.add(invoice)
    session.commit()
    return invoice


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_run_reminders_returns_summary(client):
    """POST /jobs/run-reminders returns {processed, sent, queued_for_review, errors}."""
    response = client.post("/jobs/run-reminders")
    assert response.status_code == 200
    body = response.json()
    assert "processed" in body
    assert "sent" in body
    assert "queued_for_review" in body
    assert "errors" in body
    assert isinstance(body["processed"], int)
    assert isinstance(body["sent"], int)
    assert isinstance(body["queued_for_review"], int)
    assert isinstance(body["errors"], list)


def test_run_reminders_empty_returns_zero_counts(client):
    """No overdue invoices returns {processed:0, sent:0, queued_for_review:0, errors:[]}."""
    response = client.post("/jobs/run-reminders")
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 0
    assert body["sent"] == 0
    assert body["queued_for_review"] == 0
    assert body["errors"] == []


def test_invoice_8_days_overdue_gets_level1(client, session, company_id):
    """Invoice 8 days past due_date gets level-1 reminder (fee=0, triggered_by='auto')."""
    invoice = _make_invoice(session, company_id, days_overdue=8)

    response = client.post("/jobs/run-reminders")
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 1
    assert body["errors"] == []

    # Verify the InvoiceReminder record in DB
    reminder = session.exec(
        select(InvoiceReminder).where(
            InvoiceReminder.invoice_id == invoice.id,
            InvoiceReminder.level == 1,
        )
    ).first()
    assert reminder is not None, "Level-1 reminder should have been created"
    assert reminder.fee_ore == 0
    assert reminder.triggered_by == "auto"
    assert reminder.sent_by == "scheduler"


def test_invoice_already_reminded_not_duplicated(client, session, company_id):
    """Calling the endpoint twice does not create duplicate reminders."""
    _make_invoice(session, company_id, days_overdue=8)

    response1 = client.post("/jobs/run-reminders")
    assert response1.status_code == 200
    assert response1.json()["processed"] == 1

    response2 = client.post("/jobs/run-reminders")
    assert response2.status_code == 200
    body2 = response2.json()
    # Second run: invoice already has level-1, level-2 not yet due (only 8 days) → 0 processed
    assert body2["processed"] == 0
    assert body2["errors"] == []


def test_invoice_15_days_overdue_gets_level2(client, session, company_id):
    """Invoice 15 days past due_date gets level-2 reminder (fee=REMINDER_FEE_ORE_2)."""
    invoice = _make_invoice(session, company_id, days_overdue=15)

    response = client.post("/jobs/run-reminders")
    assert response.status_code == 200
    body = response.json()
    # 15 days overdue: qualifies for both level-1 (+7d) and level-2 (+14d)
    assert body["processed"] == 2, f"Expected 2 processed (level-1 + level-2), got {body}"
    assert body["errors"] == []

    # Level-2 reminder must exist with correct fee
    reminder = session.exec(
        select(InvoiceReminder).where(
            InvoiceReminder.invoice_id == invoice.id,
            InvoiceReminder.level == 2,
        )
    ).first()
    assert reminder is not None, "Level-2 reminder should have been created"
    assert reminder.fee_ore == REMINDER_FEE_ORE_2
    assert reminder.triggered_by == "auto"
    assert reminder.sent_by == "scheduler"


def test_invoice_22_days_overdue_level3_queued_not_sent(client, session, company_id):
    """Invoice 22 days overdue: level-3 reminder created with method='manual', not auto-sent."""
    invoice = _make_invoice(session, company_id, days_overdue=22)

    response = client.post("/jobs/run-reminders")
    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    # queued_for_review must be at least 1 (the level-3)
    assert body["queued_for_review"] >= 1

    # Level-3 reminder: method='manual', triggered_by='auto'
    reminder = session.exec(
        select(InvoiceReminder).where(
            InvoiceReminder.invoice_id == invoice.id,
            InvoiceReminder.level == 3,
        )
    ).first()
    assert reminder is not None, "Level-3 reminder should have been created"
    assert reminder.method == "manual"
    assert reminder.triggered_by == "auto"
    assert reminder.sent_by == "scheduler"
    assert reminder.fee_ore == REMINDER_FEE_ORE_3


def test_paid_invoice_not_reminded(client, session, company_id):
    """Paid invoices are not included in the reminder job."""
    _make_invoice(session, company_id, days_overdue=10, status=InvoiceStatus.paid)

    response = client.post("/jobs/run-reminders")
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == 0
    assert body["sent"] == 0
    assert body["queued_for_review"] == 0
