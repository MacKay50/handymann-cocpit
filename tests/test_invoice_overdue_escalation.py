"""Phase 2 — recompute_priorities: overdue escalation tests.

Acceptance criteria covered:
  AC1  An open case whose due_date has passed is raised to priority red after recompute
  AC2  Recompute emits a priority_raised InvoiceEvent ONLY when priority actually changes
  AC3  Cases with status payment_confirmed, rejected, or handled are NOT touched
  AC4  POST /invoice-monitoring/recompute-priorities returns {"updated": N} with correct count
  AC5  Calling recompute twice on an already-escalated case does NOT emit a second event
  AC6  pytest, ruff (net-new lines), mypy green
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from haandvaerker.models.company import Company
from haandvaerker.models.invoice_case import InvoiceCase, InvoiceCaseStatus, InvoicePriority
from haandvaerker.models.invoice_event import InvoiceEvent, InvoiceEventType
from haandvaerker.services.invoice_monitoring.monitoring_service import recompute_priorities


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(name="session_esc")
def session_esc_fixture() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="company_id_esc")
def company_id_esc_fixture(session_esc: Session) -> str:
    company = Company(id=str(uuid.uuid4()), name="Eskalering Firma ApS")
    session_esc.add(company)
    session_esc.commit()
    session_esc.refresh(company)
    return company.id


def _make_open_case(
    session: Session,
    company_id: str,
    due_date: date | None,
    priority: InvoicePriority = InvoicePriority.yellow,
    status: InvoiceCaseStatus = InvoiceCaseStatus.payment_required,
    is_reminder: bool = False,
    creditor_id: str | None = None,
    confidence: float = 0.9,
    amount_ore: int = 100_000,
) -> InvoiceCase:
    """Create a minimal InvoiceCase directly — bypasses the full pipeline."""
    case = InvoiceCase(
        id=str(uuid.uuid4()),
        company_id=company_id,
        fingerprint=str(uuid.uuid4()),
        amount_ore=amount_ore,
        status=status,
        priority=priority,
        confidence=confidence,
        due_date=due_date,
        is_reminder=is_reminder,
        creditor_id=creditor_id,
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    return case


def _events_for_case(
    session: Session, case_id: str, event_type: InvoiceEventType
) -> list[InvoiceEvent]:
    return session.exec(
        select(InvoiceEvent).where(
            InvoiceEvent.invoice_case_id == case_id,
            InvoiceEvent.event_type == event_type,
        )
    ).all()


# ── AC1: overdue case is raised to red ───────────────────────────────────────

def test_overdue_case_raised_to_red(session_esc: Session, company_id_esc: str) -> None:
    """AC1 — open case with due_date in the past is escalated to red priority."""
    past_date = date.today() - timedelta(days=3)
    case = _make_open_case(
        session_esc, company_id_esc,
        due_date=past_date,
        priority=InvoicePriority.yellow,
    )

    changed = recompute_priorities(session_esc, company_id_esc)

    session_esc.refresh(case)
    assert case.priority == InvoicePriority.red, (
        f"Expected red, got {case.priority}"
    )
    assert changed >= 1


# ── AC2: event emitted ONLY when priority changes ────────────────────────────

def test_priority_raised_event_emitted_only_on_change(
    session_esc: Session, company_id_esc: str
) -> None:
    """AC2 — priority_raised event is emitted when and only when priority changes."""
    past_date = date.today() - timedelta(days=5)
    # Case that should escalate (yellow → red)
    escalating = _make_open_case(
        session_esc, company_id_esc,
        due_date=past_date,
        priority=InvoicePriority.yellow,
    )
    # Case that is already correct priority (already red, overdue)
    stable = _make_open_case(
        session_esc, company_id_esc,
        due_date=past_date,
        priority=InvoicePriority.red,
    )

    recompute_priorities(session_esc, company_id_esc)

    escalating_events = _events_for_case(
        session_esc, escalating.id, InvoiceEventType.priority_raised
    )
    stable_events = _events_for_case(session_esc, stable.id, InvoiceEventType.priority_raised)

    assert len(escalating_events) == 1, (
        f"Expected 1 priority_raised event for escalating case, got {len(escalating_events)}"
    )
    assert len(stable_events) == 0, (
        f"Expected 0 priority_raised events for stable case, got {len(stable_events)}"
    )


# ── AC3: terminal statuses are skipped ───────────────────────────────────────

def test_terminal_status_cases_not_touched(session_esc: Session, company_id_esc: str) -> None:
    """AC3 — cases with payment_confirmed, rejected, or handled are NOT modified."""
    past_date = date.today() - timedelta(days=10)

    confirmed = _make_open_case(
        session_esc, company_id_esc,
        due_date=past_date,
        priority=InvoicePriority.yellow,
        status=InvoiceCaseStatus.payment_confirmed,
    )
    rejected = _make_open_case(
        session_esc, company_id_esc,
        due_date=past_date,
        priority=InvoicePriority.yellow,
        status=InvoiceCaseStatus.rejected,
    )
    handled = _make_open_case(
        session_esc, company_id_esc,
        due_date=past_date,
        priority=InvoicePriority.yellow,
        status=InvoiceCaseStatus.handled,
    )

    changed = recompute_priorities(session_esc, company_id_esc)

    assert changed == 0, f"Expected 0 changes, got {changed}"

    for terminal_case in (confirmed, rejected, handled):
        session_esc.refresh(terminal_case)
        assert terminal_case.priority == InvoicePriority.yellow, (
            f"Terminal case {terminal_case.status} was unexpectedly modified"
        )
        events = _events_for_case(session_esc, terminal_case.id, InvoiceEventType.priority_raised)
        assert len(events) == 0


# ── AC4: HTTP endpoint returns {"updated": N} ─────────────────────────────────

def test_recompute_endpoint_returns_updated_count(
    session_esc: Session, company_id_esc: str
) -> None:
    """AC4 — POST /invoice-monitoring/recompute-priorities returns correct count."""
    from haandvaerker.api.invoice_monitoring import router
    from haandvaerker.dependencies import CompanyContext

    app = FastAPI()
    app.include_router(router)

    # Override the dependency so it uses our in-memory session
    def _override_ctx() -> CompanyContext:
        return CompanyContext(session=session_esc, company_id=company_id_esc)

    from haandvaerker.dependencies import get_company_context
    app.dependency_overrides[get_company_context] = _override_ctx

    past_date = date.today() - timedelta(days=7)
    _make_open_case(
        session_esc, company_id_esc, due_date=past_date, priority=InvoicePriority.yellow
    )
    _make_open_case(
        session_esc, company_id_esc, due_date=past_date, priority=InvoicePriority.yellow
    )
    # One that won't change (far future due date, known creditor, high confidence)
    future_date = date.today() + timedelta(days=30)
    _make_open_case(
        session_esc, company_id_esc,
        due_date=future_date,
        priority=InvoicePriority.green,
        creditor_id=str(uuid.uuid4()),
        confidence=0.95,
        amount_ore=50_000,
    )

    client = TestClient(app, raise_server_exceptions=True)
    response = client.post("/invoice-monitoring/recompute-priorities")

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "updated" in data, f"Response missing 'updated' key: {data}"
    assert data["updated"] == 2, f"Expected updated=2, got {data['updated']}"


# ── AC5: second recompute does NOT emit a duplicate event ─────────────────────

def test_second_recompute_does_not_emit_duplicate_event(
    session_esc: Session, company_id_esc: str
) -> None:
    """AC5 — calling recompute twice on an already-escalated case does not emit a second event."""
    past_date = date.today() - timedelta(days=4)
    case = _make_open_case(
        session_esc, company_id_esc,
        due_date=past_date,
        priority=InvoicePriority.yellow,
    )

    recompute_priorities(session_esc, company_id_esc)
    second_changed = recompute_priorities(session_esc, company_id_esc)

    events = _events_for_case(session_esc, case.id, InvoiceEventType.priority_raised)
    assert len(events) == 1, (
        f"Expected exactly 1 priority_raised event after two recomputes, got {len(events)}"
    )
    assert second_changed == 0, (
        f"Second recompute should have changed 0 cases, got {second_changed}"
    )


# ── Multi-tenant isolation ─────────────────────────────────────────────────────

def test_recompute_only_touches_own_company(session_esc: Session, company_id_esc: str) -> None:
    """recompute_priorities must not modify cases belonging to a different company."""
    other_company = Company(id=str(uuid.uuid4()), name="Anden Firma ApS")
    session_esc.add(other_company)
    session_esc.commit()

    past_date = date.today() - timedelta(days=5)
    other_case = _make_open_case(
        session_esc, other_company.id,
        due_date=past_date,
        priority=InvoicePriority.yellow,
    )

    recompute_priorities(session_esc, company_id_esc)

    session_esc.refresh(other_case)
    assert other_case.priority == InvoicePriority.yellow, (
        "recompute_priorities modified a case belonging to a different company"
    )
