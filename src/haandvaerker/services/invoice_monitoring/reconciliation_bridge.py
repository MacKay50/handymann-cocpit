"""InvoiceReconciliationBridge — interface stub.

This adapter defines the contract for the existing bank reconciliation module
to push payment confirmation events into the invoice monitoring module.

V1: stub implementation only. The real implementation will be wired in when
the reconciliation module is ready to emit events.

IMPORTANT: payment_confirmed status can ONLY be set through this bridge.
Normal user actions (mark_handled) must NOT set payment_confirmed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session

from ...models.invoice_case import InvoiceCase, InvoiceCaseStatus
from ...models.invoice_event import InvoiceEventType
from . import audit


def confirm_payment(
    session: Session,
    case: InvoiceCase,
    confirmed_by: str,
    amount_ore: Optional[int] = None,
) -> InvoiceCase:
    """Set status to payment_confirmed. Only callable by reconciliation module."""
    case.status = InvoiceCaseStatus.payment_confirmed
    case.updated_at = datetime.utcnow()
    session.add(case)
    audit.emit(
        session,
        case.id,
        InvoiceEventType.payment_confirmed,
        actor_type="reconciliation",
        actor_id=confirmed_by,
        payload={"confirmed_amount_ore": amount_ore},
    )
    return case


def report_payment_missing(
    session: Session,
    case: InvoiceCase,
) -> None:
    """Reconciliation reports no bank payment found after case was marked handled."""
    audit.emit(
        session,
        case.id,
        InvoiceEventType.sent_to_reconciliation,
        actor_type="reconciliation",
        payload={"result": "payment_missing"},
    )


def report_amount_mismatch(
    session: Session,
    case: InvoiceCase,
    expected_ore: int,
    actual_ore: int,
) -> None:
    """Reconciliation reports a bank payment with a different amount."""
    audit.emit(
        session,
        case.id,
        InvoiceEventType.sent_to_reconciliation,
        actor_type="reconciliation",
        payload={
            "result": "amount_mismatch",
            "expected_ore": expected_ore,
            "actual_ore": actual_ore,
        },
    )


def report_payment_date_after_due(
    session: Session,
    case: InvoiceCase,
    payment_date: str,
) -> None:
    """Reconciliation reports payment arrived after the due date."""
    audit.emit(
        session,
        case.id,
        InvoiceEventType.sent_to_reconciliation,
        actor_type="reconciliation",
        payload={"result": "payment_date_after_due", "payment_date": payment_date},
    )
