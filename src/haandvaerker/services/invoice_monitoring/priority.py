"""InvoicePriorityService — deterministic priority assignment.

Rules (evaluated top-to-bottom, first match wins):
  red:    overdue | due today | due within 2 days | is_reminder
  orange: due within 7 days | unknown creditor | confidence < 0.6 | amount > threshold
  yellow: due within 14 days | missing amount
  green:  due > 14 days AND known creditor AND confidence >= 0.8
  yellow: fallback
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from ...models.invoice_case import InvoicePriority

# Amount threshold: 10.000 kr = 1_000_000 øre (configurable via env; import lazily to avoid
# circular imports at module load time)
_DEFAULT_HIGH_AMOUNT_ORE = 1_000_000


def _high_amount_threshold() -> int:
    try:
        from .... config import ENV  # noqa: F401 — side effect: load dotenv
        import os
        return int(os.getenv("INVOICE_HIGH_AMOUNT_ORE", str(_DEFAULT_HIGH_AMOUNT_ORE)))
    except Exception:
        return _DEFAULT_HIGH_AMOUNT_ORE


def compute_priority(
    due_date: Optional[date],
    is_reminder: bool,
    creditor_id: Optional[str],
    confidence: float,
    amount_ore: int,
) -> InvoicePriority:
    today = date.today()

    # ── red ───────────────────────────────────────────────────────────────────
    if is_reminder:
        return InvoicePriority.red
    if due_date is not None:
        days_until_due = (due_date - today).days
        if days_until_due <= 2:  # overdue (negative) or due today/within 2 days
            return InvoicePriority.red

    # ── orange ────────────────────────────────────────────────────────────────
    if due_date is not None and (due_date - today).days <= 7:
        return InvoicePriority.orange
    if creditor_id is None:
        return InvoicePriority.orange
    if confidence < 0.6:
        return InvoicePriority.orange
    if amount_ore > _high_amount_threshold():
        return InvoicePriority.orange

    # ── yellow ────────────────────────────────────────────────────────────────
    if due_date is not None and (due_date - today).days <= 14:
        return InvoicePriority.yellow
    if amount_ore == 0:
        return InvoicePriority.yellow

    # ── green ─────────────────────────────────────────────────────────────────
    if (
        due_date is not None
        and (due_date - today).days > 14
        and creditor_id is not None
        and confidence >= 0.8
    ):
        return InvoicePriority.green

    return InvoicePriority.yellow
