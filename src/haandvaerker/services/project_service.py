"""Project completion policy — checklist for closing a project."""
from dataclasses import dataclass, field
from sqlmodel import Session, select
from ..models.action_item import ActionItem, ActionItemStatus
from ..models.expense import Expense
from ..models.invoice import Invoice, InvoiceStatus
from ..models.time_entry import TimeEntry


@dataclass
class CompletionBlocker:
    type: str
    detail: str


@dataclass
class CompletionStatus:
    ready: bool
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def check_completion_status(session: Session, project_id: str) -> CompletionStatus:
    """Return completion checklist for the given project.

    Blockers (all must be clear for ready=True):
    1. No unbilled billable TimeEntries (billable=True, invoice_id=None, active=True)
    2. No unbilled billable Expenses (billable=True, invoice_id=None, active=True)
    3. At least one paid Invoice, OR no invoices at all

    Warnings (soft — do not block completion):
    4. Open or in-progress ActionItems exist (active=True)
    """
    blockers: list[CompletionBlocker] = []
    warnings: list[str] = []

    # 1 — Unbilled billable time entries
    unbilled_entries = session.exec(
        select(TimeEntry).where(
            TimeEntry.project_id == project_id,
            TimeEntry.billable.is_(True),
            TimeEntry.invoice_id.is_(None),
            TimeEntry.active.is_(True),
        )
    ).all()
    if unbilled_entries:
        blockers.append(CompletionBlocker(
            type="unbilled_time_entries",
            detail=f"{len(unbilled_entries)} fakturérbare timer mangler at blive faktureret.",
        ))

    # 2 — Unbilled billable expenses
    unbilled_expenses = session.exec(
        select(Expense).where(
            Expense.project_id == project_id,
            Expense.billable.is_(True),
            Expense.invoice_id.is_(None),
            Expense.active.is_(True),
        )
    ).all()
    if unbilled_expenses:
        blockers.append(CompletionBlocker(
            type="unbilled_expenses",
            detail=f"{len(unbilled_expenses)} fakturérbare udlæg mangler at blive faktureret.",
        ))

    # 3 — Payment received (or no invoices created at all)
    invoices = session.exec(
        select(Invoice).where(
            Invoice.project_id == project_id,
            Invoice.active.is_(True),
        )
    ).all()
    if invoices:
        has_paid = any(inv.status == InvoiceStatus.paid for inv in invoices)
        if not has_paid:
            blockers.append(CompletionBlocker(
                type="no_paid_invoice",
                detail="Ingen fakturaer er markeret som betalt.",
            ))

    # 4 — Open action items (warning only, non-blocking)
    open_items = session.exec(
        select(ActionItem).where(
            ActionItem.project_id == project_id,
            ActionItem.status.in_([ActionItemStatus.open, ActionItemStatus.in_progress]),
            ActionItem.active.is_(True),
        )
    ).all()
    if open_items:
        warnings.append(
            f"{len(open_items)} åbne opgave(r) på projektet."
        )

    return CompletionStatus(
        ready=len(blockers) == 0,
        blockers=blockers,
        warnings=warnings,
    )
