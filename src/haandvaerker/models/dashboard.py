from __future__ import annotations
from typing import Optional
from sqlmodel import SQLModel
from .admin_deadline import AdminDeadlineRead


class DashboardRead(SQLModel):
    company_id: str
    inbox_unread: int
    enquiries_new: int
    enquiries_qualified: int
    projects_draft: int
    projects_active: int
    quotes_awaiting: int
    quotes_accepted: int
    quotes_win_rate: Optional[float]
    invoices_draft: int
    invoices_outstanding: float
    invoices_overdue_count: int
    invoices_overdue_amount: float
    reminders_pending: int
    deadlines_overdue: list[AdminDeadlineRead]
    deadlines_upcoming: list[AdminDeadlineRead]
    reconciliation_unmatched_invoices: int
    reconciliation_overdue_invoices: int
    reconciliation_overdue_amount_ore: int
