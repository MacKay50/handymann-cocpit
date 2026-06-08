"""InvoiceDuplicateService — fingerprint-based duplicate and reminder detection.

Fingerprint = sha256 of: normalized(creditor_name) + invoice_number + amount_ore
              + currency + due_date + payment_reference

Rules:
- Same fingerprint as an existing active case → duplicate
- is_reminder=True + matching fingerprint → reminder on existing case
  (raises priority to red, creates reminder_received event, does NOT create
   a new independent payment action)
"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlmodel import Session, select

from ...models.invoice_case import InvoiceCase, InvoiceCaseStatus, InvoicePriority


def compute_fingerprint(
    creditor_name: Optional[str],
    invoice_number: Optional[str],
    amount_ore: int,
    currency: str,
    due_date: Optional[object],  # date or None
    payment_reference: Optional[str],
) -> str:
    parts = [
        _norm(creditor_name),
        _norm(invoice_number),
        str(amount_ore),
        currency.upper(),
        str(due_date) if due_date else "",
        _norm(payment_reference),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def _norm(s: Optional[str]) -> str:
    if not s:
        return ""
    return s.strip().lower()


def find_existing_case(
    session: Session,
    company_id: str,
    fingerprint: str,
) -> Optional[InvoiceCase]:
    """Return the most recent active case with this fingerprint, or None."""
    return session.exec(
        select(InvoiceCase).where(
            InvoiceCase.company_id == company_id,
            InvoiceCase.fingerprint == fingerprint,
            InvoiceCase.active == True,  # noqa: E712
        )
    ).first()


def handle_reminder_on_existing(
    session: Session,
    existing_case: InvoiceCase,
    reminder_level: Optional[int],
) -> InvoiceCase:
    """Upgrade an existing case when a reminder arrives for it."""
    existing_case.priority = InvoicePriority.red
    existing_case.is_reminder = True
    if reminder_level is not None:
        existing_case.reminder_level = reminder_level
    existing_case.status = InvoiceCaseStatus.reminder_received
    from datetime import datetime
    existing_case.updated_at = datetime.utcnow()
    session.add(existing_case)
    return existing_case
