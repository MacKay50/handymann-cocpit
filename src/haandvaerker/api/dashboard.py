from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.admin_deadline import AdminDeadline, AdminDeadlineRead, DeadlineStatus
from ..models.dashboard import DashboardRead
from ..models.economic_invoice import EconomicInvoice, EconomicInvoiceStatus
from ..models.enquiry import Enquiry, EnquiryStatus
from ..models.inbox_message import InboxMessage, InboxStatus
from ..models.invoice import Invoice, InvoiceStatus
from ..models.project import Project, ProjectStatus
from ..models.quote import Quote, QuoteStatus
from ..models.reminder import Reminder, ReminderStatus
from ..utils import to_decimal

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


UPCOMING_DAYS = 14


@router.get("", response_model=DashboardRead)
def get_dashboard(ctx: CompanyContextDep) -> DashboardRead:
    session = ctx.session
    company_id = ctx.company_id

    today = date.today()
    upcoming_cutoff = today + timedelta(days=UPCOMING_DAYS)
    q = Decimal("0.01")
    zero = Decimal("0")

    inbox_unread = len(session.exec(
        select(InboxMessage)
        .where(InboxMessage.company_id == company_id)
        .where(InboxMessage.active == True)  # noqa: E712
        .where(InboxMessage.status == InboxStatus.unread)
    ).all())

    enquiries_new = len(session.exec(
        select(Enquiry)
        .where(Enquiry.company_id == company_id)
        .where(Enquiry.active == True)  # noqa: E712
        .where(Enquiry.status == EnquiryStatus.new)
    ).all())

    enquiries_qualified = len(session.exec(
        select(Enquiry)
        .where(Enquiry.company_id == company_id)
        .where(Enquiry.active == True)  # noqa: E712
        .where(Enquiry.status == EnquiryStatus.qualified)
    ).all())

    projects_draft = len(session.exec(
        select(Project)
        .where(Project.company_id == company_id)
        .where(Project.active == True)  # noqa: E712
        .where(Project.status == ProjectStatus.draft)
    ).all())

    projects_active = len(session.exec(
        select(Project)
        .where(Project.company_id == company_id)
        .where(Project.active == True)  # noqa: E712
        .where(Project.status == ProjectStatus.active)
    ).all())

    quotes_awaiting = len(session.exec(
        select(Quote)
        .where(Quote.company_id == company_id)
        .where(Quote.active == True)  # noqa: E712
        .where(Quote.status == QuoteStatus.sent)
    ).all())

    quotes_accepted = len(session.exec(
        select(Quote)
        .where(Quote.company_id == company_id)
        .where(Quote.active == True)  # noqa: E712
        .where(Quote.status == QuoteStatus.accepted)
    ).all())

    quotes_rejected = len(session.exec(
        select(Quote)
        .where(Quote.company_id == company_id)
        .where(Quote.active == True)  # noqa: E712
        .where(Quote.status == QuoteStatus.rejected)
    ).all())

    closed = quotes_accepted + quotes_rejected
    quotes_win_rate = round(quotes_accepted / closed * 100, 1) if closed > 0 else None

    draft_invoices = session.exec(
        select(Invoice)
        .where(Invoice.company_id == company_id)
        .where(Invoice.active == True)  # noqa: E712
        .where(Invoice.status == InvoiceStatus.draft)
    ).all()
    invoices_draft = len(draft_invoices)

    sent_invoices = session.exec(
        select(Invoice)
        .where(Invoice.company_id == company_id)
        .where(Invoice.active == True)  # noqa: E712
        .where(Invoice.status == InvoiceStatus.sent)
    ).all()

    invoices_outstanding = float(
        sum((to_decimal(inv.total) for inv in sent_invoices), zero).quantize(q, ROUND_HALF_UP)
    )

    overdue = [inv for inv in sent_invoices if inv.due_date < today]
    invoices_overdue_count = len(overdue)
    invoices_overdue_amount = float(
        sum((to_decimal(inv.total) for inv in overdue), zero).quantize(q, ROUND_HALF_UP)
    )

    reminders_pending = len(session.exec(
        select(Reminder)
        .where(Reminder.company_id == company_id)
        .where(Reminder.active == True)  # noqa: E712
        .where(Reminder.status == ReminderStatus.pending)
    ).all())

    overdue_deadlines = session.exec(
        select(AdminDeadline)
        .where(AdminDeadline.company_id == company_id)
        .where(AdminDeadline.active == True)  # noqa: E712
        .where(AdminDeadline.status == DeadlineStatus.pending)
        .where(AdminDeadline.due_date < today)
        .order_by(AdminDeadline.due_date)
    ).all()

    upcoming_deadlines = session.exec(
        select(AdminDeadline)
        .where(AdminDeadline.company_id == company_id)
        .where(AdminDeadline.active == True)  # noqa: E712
        .where(AdminDeadline.status == DeadlineStatus.pending)
        .where(AdminDeadline.due_date >= today)
        .where(AdminDeadline.due_date <= upcoming_cutoff)
        .order_by(AdminDeadline.due_date)
    ).all()

    unmatched_invoices_q = session.exec(
        select(EconomicInvoice)
        .where(EconomicInvoice.company_id == company_id)
        .where(EconomicInvoice.active == True)  # noqa: E712
        .where(EconomicInvoice.status == EconomicInvoiceStatus.unmatched)
    ).all()
    reconciliation_unmatched_invoices = len(unmatched_invoices_q)

    overdue_invoices = [inv for inv in unmatched_invoices_q if inv.due_date < today]
    reconciliation_overdue_invoices = len(overdue_invoices)
    reconciliation_overdue_amount_ore = sum(inv.gross_amount_ore for inv in overdue_invoices)

    return DashboardRead(
        company_id=company_id,
        inbox_unread=inbox_unread,
        enquiries_new=enquiries_new,
        enquiries_qualified=enquiries_qualified,
        projects_draft=projects_draft,
        projects_active=projects_active,
        quotes_awaiting=quotes_awaiting,
        quotes_accepted=quotes_accepted,
        quotes_win_rate=quotes_win_rate,
        invoices_draft=invoices_draft,
        invoices_outstanding=invoices_outstanding,
        invoices_overdue_count=invoices_overdue_count,
        invoices_overdue_amount=invoices_overdue_amount,
        reminders_pending=reminders_pending,
        deadlines_overdue=[AdminDeadlineRead.model_validate(d) for d in overdue_deadlines],
        deadlines_upcoming=[AdminDeadlineRead.model_validate(d) for d in upcoming_deadlines],
        reconciliation_unmatched_invoices=reconciliation_unmatched_invoices,
        reconciliation_overdue_invoices=reconciliation_overdue_invoices,
        reconciliation_overdue_amount_ore=reconciliation_overdue_amount_ore,
    )
