"""Admin job endpoints — triggered by OS-level scheduler (Windows Task Scheduler / cron).

NOTE: This endpoint is not protected by authentication beyond the session cookie.
It should be network-restricted in production (internal-only) or called by the server itself.
"""
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from ..dependencies import CompanyContextDep
from ..services.invoice_reminder_service import run_automatic_reminders

router = APIRouter(prefix="/jobs", tags=["jobs"])


class ReminderJobResult(BaseModel):
    processed: int
    sent: int
    queued_for_review: int
    errors: list[str]


@router.post("/run-reminders", response_model=ReminderJobResult)
def run_reminders(ctx: CompanyContextDep) -> ReminderJobResult:
    """Find all overdue invoices and automatically send/queue reminders.

    Thresholds (days past due_date for status='sent' invoices):
      +7d  → level-1 reminder (fee=0, auto-sent)
      +14d → level-2 reminder (fee=REMINDER_FEE_ORE_2, auto-sent)
      +21d → level-3 reminder (fee=REMINDER_FEE_ORE_3, method='manual' — queued for review)

    Idempotent: existing (invoice_id, level) dedup prevents duplicates on re-run.
    """
    result = run_automatic_reminders(
        session=ctx.session,
        company_id=ctx.company_id,
        today=date.today(),
    )
    return ReminderJobResult(**result)
