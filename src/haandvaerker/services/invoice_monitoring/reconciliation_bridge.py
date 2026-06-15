"""InvoiceReconciliationBridge — debit bank matcher + payment confirmation.

This adapter:
  1. Defines confirm_payment — the ONLY path to payment_confirmed status.
  2. Provides match_debit_transaction — deterministic debit matcher that
     auto-confirms on exact match of amount + bank_reference + date window.

Iron Law 3: code decides. Auto-confirm fires ONLY on exact match of ALL three
criteria. Any partial match → no auto-confirm.

Iron Law 2: no masking fallbacks. All failure paths are explicit.

IMPORTANT: payment_confirmed status can ONLY be set through confirm_payment.
Normal user actions (mark_handled) must NOT set payment_confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ...models.bank_transaction import BankTransaction
from ...models.invoice_case import InvoiceCase, InvoiceCaseStatus
from ...models.invoice_event import InvoiceEventType
from . import audit

_DATE_WINDOW_DAYS = 7

# Statuses that mean a case is closed / terminal — do not re-match.
_TERMINAL_STATUSES = frozenset({
    InvoiceCaseStatus.payment_confirmed,
    InvoiceCaseStatus.rejected,
    InvoiceCaseStatus.handled,
    InvoiceCaseStatus.not_relevant,
    InvoiceCaseStatus.duplicate,
})


@dataclass
class MatchResult:
    """Result returned by match_debit_transaction."""
    matched: bool
    auto_confirmed: bool
    case_id: Optional[str] = field(default=None)
    needs_review: bool = field(default=False)


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


def match_debit_transaction(
    session: Session,
    bank_transaction: BankTransaction,
    company_id: str,
) -> MatchResult:
    """Match a debit bank transaction against open InvoiceCases.

    Auto-confirms ONLY on exact match of ALL three criteria (Iron Law 3):
      1. Exact amount: abs(bank_transaction.amount_ore) == case.amount_ore
      2. Payment reference: bank_transaction.bank_reference == case.payment_reference
         (criterion skipped only when BOTH are None/empty; if either has a value,
          they must match exactly)
      3. Date within 7 days: abs((tx.transaction_date - case.due_date).days) <= 7
         (criterion skipped when case.due_date is None)

    Partial match (amount matches but reference or date fails): case is set to
    reconciliation_pending and a sent_to_reconciliation event is emitted so the
    operator can review it.  Does NOT auto-confirm (Iron Law 3).

    Does NOT commit — caller commits.

    Args:
        session: Active SQLModel session.
        bank_transaction: The debit transaction to match. Must have amount_ore < 0.
        company_id: Company scope for multi-tenant isolation.

    Returns:
        MatchResult(matched=True, auto_confirmed=True, case_id=...) on exact match.
        MatchResult(matched=False, auto_confirmed=False, needs_review=True) on partial match.
        MatchResult(matched=False, auto_confirmed=False) when no amount match.
    """
    # Must be a debit transaction
    if bank_transaction.amount_ore >= 0:
        return MatchResult(matched=False, auto_confirmed=False)

    debit_amount = abs(bank_transaction.amount_ore)

    open_cases = session.exec(
        select(InvoiceCase).where(
            InvoiceCase.company_id == company_id,
            InvoiceCase.amount_ore == debit_amount,
            InvoiceCase.active == True,
            InvoiceCase.status.not_in(list(_TERMINAL_STATUSES)),  # type: ignore[attr-defined]
        )
    ).all()

    for case in open_cases:
        # Criterion 2: payment reference
        # Skip ONLY when BOTH are empty; if either has a value they must match exactly.
        tx_ref = (bank_transaction.bank_reference or "").strip()
        case_ref = (case.payment_reference or "").strip()
        if (tx_ref or case_ref) and tx_ref != case_ref:
            continue

        # Criterion 3: date window (only when case.due_date is set)
        if case.due_date is not None:
            delta = abs((bank_transaction.transaction_date - case.due_date).days)
            if delta > _DATE_WINDOW_DAYS:
                continue

        # All criteria satisfied — auto-confirm (Iron Law 3: exact match only)
        confirm_payment(
            session,
            case,
            confirmed_by="debit_matcher",
            amount_ore=debit_amount,
        )
        return MatchResult(matched=True, auto_confirmed=True, case_id=case.id)

    # Amount matched but at least one secondary criterion failed → partial match.
    # Mark each case as reconciliation_pending so the operator sees it.
    if open_cases:
        for case in open_cases:
            case.status = InvoiceCaseStatus.reconciliation_pending
            case.updated_at = datetime.utcnow()
            session.add(case)
            audit.emit(
                session,
                case.id,
                InvoiceEventType.sent_to_reconciliation,
                actor_type="reconciliation",
                payload={"result": "partial_match"},
            )
        return MatchResult(matched=False, auto_confirmed=False, needs_review=True)

    return MatchResult(matched=False, auto_confirmed=False)
