"""Betalingsradar — invoice monitoring API.

Route registration order (fixed paths BEFORE /{case_id}):
  1. GET  /invoice-monitoring/action-items
  2. GET  /invoice-monitoring/cases
  3. GET  /invoice-monitoring/creditors
  4. POST /invoice-monitoring/dev/ingest-sample   (dev/test only)
  5. POST /invoice-monitoring/recompute-priorities
  6. GET  /invoice-monitoring/cases/{case_id}
  7. POST /invoice-monitoring/cases/{case_id}/open-bank
  8. POST /invoice-monitoring/cases/{case_id}/mark-handled
  9. POST /invoice-monitoring/cases/{case_id}/reject
 10. POST /invoice-monitoring/cases/{case_id}/mark-duplicate
 11. PATCH /invoice-monitoring/cases/{case_id}/fields

Permissions: defined as constants, not enforced in V1.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..config import ENV
from ..dependencies import CompanyContextDep
from ..models.creditor import Creditor, CreditorRead
from ..models.extraction_evidence import ExtractionEvidence
from ..models.invoice_action_item import InvoiceActionItem, InvoiceActionItemStatus
from ..models.invoice_case import InvoiceCase, InvoiceCaseStatus, InvoicePriority
from ..models.invoice_event import InvoiceEvent, InvoiceEventType
from ..services.invoice_monitoring import audit
from ..services.invoice_monitoring.monitoring_service import (
    ingest_sample as _ingest_sample,
    recompute_priorities as _recompute_priorities,
)
from ..services.invoice_monitoring.priority import compute_priority

router = APIRouter(prefix="/invoice-monitoring", tags=["invoice-monitoring"])

# ── permission stubs (not enforced in V1) ─────────────────────────────────────
PERM_VIEW = "invoice_monitoring.view"
PERM_MANAGE = "invoice_monitoring.manage"
PERM_MARK_HANDLED = "invoice_monitoring.mark_handled"
PERM_ADMIN = "invoice_monitoring.admin"

# Danske Bank Netbank URL — not automated, opened in browser by the user
_BANK_URL = "https://netbank.danskebank.dk/"


# ── response models ────────────────────────────────────────────────────────────

class EvidenceRead(BaseModel):
    id: str
    field_name: str
    extracted_value: Optional[str]
    source_text: Optional[str]
    confidence: float
    created_at: datetime


class EventRead(BaseModel):
    id: str
    event_type: str
    actor_type: str
    actor_id: Optional[str]
    payload: Optional[dict]
    created_at: datetime


class ActionItemRead(BaseModel):
    id: str
    invoice_case_id: str
    company_id: str
    status: str
    due_date: Optional[date]
    handled_by: Optional[str]
    handled_at: Optional[datetime]
    active: bool
    created_at: datetime
    # Denormalised from case for list view
    priority: Optional[str] = None
    amount_ore: Optional[int] = None
    creditor_name: Optional[str] = None
    invoice_number: Optional[str] = None


class InvoiceCaseRead(BaseModel):
    id: str
    company_id: str
    creditor_id: Optional[str]
    creditor_name_raw: Optional[str]
    invoice_number: Optional[str]
    amount_ore: int
    currency: str
    invoice_date: Optional[date]
    due_date: Optional[date]
    payment_reference: Optional[str]
    status: str
    priority: str
    confidence: float
    is_reminder: bool
    reminder_level: Optional[int]
    active: bool
    created_at: datetime
    updated_at: datetime


class InvoiceCaseDetailRead(InvoiceCaseRead):
    evidence: list[EvidenceRead]
    events: list[EventRead]
    action_item: Optional[ActionItemRead]


class IngestSampleRequest(BaseModel):
    subject: str
    sender: str
    body_text: str
    amount_ore: Optional[int] = None
    invoice_number: Optional[str] = None
    due_date: Optional[date] = None
    creditor_name: Optional[str] = None


class MarkDuplicateRequest(BaseModel):
    duplicate_of_case_id: str


class FieldCorrectionRequest(BaseModel):
    field_name: str
    new_value: str


# ── helpers ────────────────────────────────────────────────────────────────────

def _get_case_or_404(session: Session, case_id: str) -> InvoiceCase:
    case = session.get(InvoiceCase, case_id)
    if not case or not case.active:
        raise HTTPException(status_code=404, detail=f"InvoiceCase '{case_id}' ikke fundet")
    return case


def _case_to_read(case: InvoiceCase) -> InvoiceCaseRead:
    return InvoiceCaseRead(
        id=case.id,
        company_id=case.company_id,
        creditor_id=case.creditor_id,
        creditor_name_raw=case.creditor_name_raw,
        invoice_number=case.invoice_number,
        amount_ore=case.amount_ore,
        currency=case.currency,
        invoice_date=case.invoice_date,
        due_date=case.due_date,
        payment_reference=case.payment_reference,
        status=case.status.value,
        priority=case.priority.value,
        confidence=case.confidence,
        is_reminder=case.is_reminder,
        reminder_level=case.reminder_level,
        active=case.active,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


_PRIORITY_ORDER = {
    InvoicePriority.red: 0,
    InvoicePriority.orange: 1,
    InvoicePriority.yellow: 2,
    InvoicePriority.green: 3,
}


# ── 1. GET /invoice-monitoring/action-items ────────────────────────────────────

@router.get("/action-items", response_model=list[ActionItemRead])
def list_action_items(ctx: CompanyContextDep) -> list[ActionItemRead]:
    """Active action items sorted by priority (red first) then due_date."""
    session = ctx.session
    company_id = ctx.company_id

    items = session.exec(
        select(InvoiceActionItem).where(
            InvoiceActionItem.company_id == company_id,
            InvoiceActionItem.active == True,  # noqa: E712
            InvoiceActionItem.status == InvoiceActionItemStatus.open,
        )
    ).all()

    result: list[ActionItemRead] = []
    for item in items:
        case = session.get(InvoiceCase, item.invoice_case_id)
        result.append(ActionItemRead(
            id=item.id,
            invoice_case_id=item.invoice_case_id,
            company_id=item.company_id,
            status=item.status.value,
            due_date=item.due_date,
            handled_by=item.handled_by,
            handled_at=item.handled_at,
            active=item.active,
            created_at=item.created_at,
            priority=case.priority.value if case else None,
            amount_ore=case.amount_ore if case else None,
            creditor_name=case.creditor_name_raw if case else None,
            invoice_number=case.invoice_number if case else None,
        ))

    result.sort(key=lambda x: (
        _PRIORITY_ORDER.get(InvoicePriority(x.priority), 9) if x.priority else 9,
        x.due_date or date.max,
    ))
    return result


# ── 2. GET /invoice-monitoring/cases ─────────────────────────────────────────

@router.get("/cases", response_model=list[InvoiceCaseRead])
def list_cases(
    ctx: CompanyContextDep,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    creditor_id: Optional[str] = None,
    due_before: Optional[date] = None,
    due_after: Optional[date] = None,
) -> list[InvoiceCaseRead]:
    session = ctx.session
    company_id = ctx.company_id

    q = select(InvoiceCase).where(
        InvoiceCase.company_id == company_id,
        InvoiceCase.active == True,  # noqa: E712
    )
    if status:
        try:
            q = q.where(InvoiceCase.status == InvoiceCaseStatus(status))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Ukendt status: {status}")
    if priority:
        try:
            q = q.where(InvoiceCase.priority == InvoicePriority(priority))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Ukendt prioritet: {priority}")
    if creditor_id:
        q = q.where(InvoiceCase.creditor_id == creditor_id)
    if due_before:
        q = q.where(InvoiceCase.due_date <= due_before)
    if due_after:
        q = q.where(InvoiceCase.due_date >= due_after)

    return [_case_to_read(c) for c in session.exec(q).all()]


# ── 3. GET /invoice-monitoring/creditors ─────────────────────────────────────

@router.get("/creditors", response_model=list[CreditorRead])
def list_creditors(ctx: CompanyContextDep) -> list[CreditorRead]:
    session = ctx.session
    creditors = session.exec(
        select(Creditor).where(
            Creditor.company_id == ctx.company_id,
            Creditor.active == True,  # noqa: E712
        )
    ).all()
    return [
        CreditorRead(
            id=c.id,
            company_id=c.company_id,
            name=c.name,
            cvr_number=c.cvr_number,
            default_category=c.default_category,
            risk_level=c.risk_level,
            active=c.active,
            created_at=c.created_at,
        )
        for c in creditors
    ]


# ── 4. POST /invoice-monitoring/dev/ingest-sample ────────────────────────────

@router.post("/dev/ingest-sample", status_code=201)
def dev_ingest_sample(body: IngestSampleRequest, ctx: CompanyContextDep) -> dict:
    """Dev/test-only endpoint. Returns 403 outside development environment."""
    if ENV not in ("development", "test"):
        raise HTTPException(status_code=403, detail="Kun tilgængelig i udviklingsmiljø")

    session = ctx.session
    result = _ingest_sample(
        session=session,
        company_id=ctx.company_id,
        subject=body.subject,
        sender=body.sender,
        body_text=body.body_text,
        amount_ore=body.amount_ore,
        invoice_number=body.invoice_number,
        due_date=body.due_date,
        creditor_name=body.creditor_name,
    )
    return {
        "mail_message_id": result.mail_message_id,
        "invoice_case_id": result.invoice_case_id,
        "action_item_id": result.action_item_id,
        "is_relevant": result.is_relevant,
        "is_duplicate": result.is_duplicate,
        "is_reminder": result.is_reminder,
        "priority": result.priority,
        "status": result.status,
    }


# ── 5. POST /invoice-monitoring/recompute-priorities ─────────────────────────

@router.post("/recompute-priorities")
def recompute_priorities_endpoint(ctx: CompanyContextDep) -> dict:
    """Daily/on-demand recompute: escalates open cases toward red as due dates approach."""
    updated = _recompute_priorities(ctx.session, ctx.company_id)
    return {"updated": updated}


# ── 6. GET /invoice-monitoring/cases/{case_id} ────────────────────────────────

@router.get("/cases/{case_id}", response_model=InvoiceCaseDetailRead)
def get_case(case_id: str, ctx: CompanyContextDep) -> InvoiceCaseDetailRead:
    session = ctx.session
    case = _get_case_or_404(session, case_id)
    if case.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    evidence = session.exec(
        select(ExtractionEvidence).where(ExtractionEvidence.invoice_case_id == case_id)
    ).all()
    events = session.exec(
        select(InvoiceEvent).where(InvoiceEvent.invoice_case_id == case_id)
        .order_by(InvoiceEvent.created_at)
    ).all()
    action_item = session.exec(
        select(InvoiceActionItem).where(
            InvoiceActionItem.invoice_case_id == case_id,
            InvoiceActionItem.active == True,  # noqa: E712
        )
    ).first()

    return InvoiceCaseDetailRead(
        **_case_to_read(case).model_dump(),
        evidence=[
            EvidenceRead(
                id=e.id,
                field_name=e.field_name,
                extracted_value=e.extracted_value,
                source_text=e.source_text,
                confidence=e.confidence,
                created_at=e.created_at,
            )
            for e in evidence
        ],
        events=[
            EventRead(
                id=ev.id,
                event_type=ev.event_type.value,
                actor_type=ev.actor_type,
                actor_id=ev.actor_id,
                payload=json.loads(ev.payload) if ev.payload else None,
                created_at=ev.created_at,
            )
            for ev in events
        ],
        action_item=(
            ActionItemRead(
                id=action_item.id,
                invoice_case_id=action_item.invoice_case_id,
                company_id=action_item.company_id,
                status=action_item.status.value,
                due_date=action_item.due_date,
                handled_by=action_item.handled_by,
                handled_at=action_item.handled_at,
                active=action_item.active,
                created_at=action_item.created_at,
            )
            if action_item else None
        ),
    )


# ── 6. POST /invoice-monitoring/cases/{case_id}/open-bank ────────────────────

@router.post("/cases/{case_id}/open-bank")
def open_bank(case_id: str, ctx: CompanyContextDep) -> dict:
    """Records that the user opened Netbank. Sets status to bank_opened."""
    session = ctx.session
    case = _get_case_or_404(session, case_id)
    if case.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if case.status not in (
        InvoiceCaseStatus.payment_required,
        InvoiceCaseStatus.reminder_received,
        InvoiceCaseStatus.needs_review,
        InvoiceCaseStatus.bank_opened,
    ):
        raise HTTPException(
            status_code=422,
            detail=f"Kan ikke åbne bank fra status '{case.status.value}'",
        )

    case.status = InvoiceCaseStatus.bank_opened
    case.updated_at = datetime.utcnow()
    session.add(case)

    action_item = session.exec(
        select(InvoiceActionItem).where(
            InvoiceActionItem.invoice_case_id == case_id,
            InvoiceActionItem.active == True,  # noqa: E712
        )
    ).first()
    if action_item:
        action_item.status = InvoiceActionItemStatus.bank_opened
        action_item.updated_at = datetime.utcnow()
        session.add(action_item)

    audit.emit(session, case_id, InvoiceEventType.bank_opened,
               actor_type="user",
               payload={"bank_url": _BANK_URL})
    session.commit()

    return {"bank_url": _BANK_URL, "status": case.status.value}


# ── 7. POST /invoice-monitoring/cases/{case_id}/mark-handled ─────────────────

@router.post("/cases/{case_id}/mark-handled")
def mark_handled(
    case_id: str,
    ctx: CompanyContextDep,
    handled_by: str = "user",
) -> dict:
    """Mark the case as handled."""
    session = ctx.session
    case = _get_case_or_404(session, case_id)
    if case.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if case.status in (InvoiceCaseStatus.payment_confirmed, InvoiceCaseStatus.rejected):
        raise HTTPException(
            status_code=422,
            detail=f"Kan ikke markere håndteret fra status '{case.status.value}'",
        )

    now = datetime.utcnow()
    case.status = InvoiceCaseStatus.handled
    case.updated_at = now
    session.add(case)

    action_item = session.exec(
        select(InvoiceActionItem).where(
            InvoiceActionItem.invoice_case_id == case_id,
            InvoiceActionItem.active == True,  # noqa: E712
        )
    ).first()
    if action_item:
        action_item.status = InvoiceActionItemStatus.handled
        action_item.handled_by = handled_by
        action_item.handled_at = now
        action_item.updated_at = now
        session.add(action_item)

    audit.emit(session, case_id, InvoiceEventType.marked_handled,
               actor_type="user", actor_id=handled_by,
               payload={"note": "Håndteret betyder ikke nødvendigvis betalt. Betaling bekræftes via fakturaafstemning."})
    session.commit()

    return {
        "id": case_id,
        "status": case.status.value,
        "handled_by": handled_by,
        "handled_at": now.isoformat(),
        "note": "Håndteret betyder ikke nødvendigvis betalt. Betaling bekræftes via fakturaafstemning.",
    }


# ── 8. POST /invoice-monitoring/cases/{case_id}/reject ───────────────────────

@router.post("/cases/{case_id}/reject")
def reject_case(case_id: str, ctx: CompanyContextDep, reason: Optional[str] = None) -> dict:
    """Reject a false positive or irrelevant invoice."""
    session = ctx.session
    case = _get_case_or_404(session, case_id)
    if case.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    case.status = InvoiceCaseStatus.rejected
    case.updated_at = datetime.utcnow()
    session.add(case)

    action_item = session.exec(
        select(InvoiceActionItem).where(
            InvoiceActionItem.invoice_case_id == case_id,
            InvoiceActionItem.active == True,  # noqa: E712
        )
    ).first()
    if action_item:
        action_item.status = InvoiceActionItemStatus.rejected
        action_item.active = False
        action_item.updated_at = datetime.utcnow()
        session.add(action_item)

    audit.emit(session, case_id, InvoiceEventType.rejected,
               actor_type="user",
               payload={"reason": reason})
    session.commit()

    return {"id": case_id, "status": case.status.value}


# ── 9. POST /invoice-monitoring/cases/{case_id}/mark-duplicate ───────────────

@router.post("/cases/{case_id}/mark-duplicate")
def mark_duplicate(case_id: str, body: MarkDuplicateRequest, ctx: CompanyContextDep) -> dict:
    """Mark as duplicate of an existing case."""
    session = ctx.session
    case = _get_case_or_404(session, case_id)
    if case.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    original = session.get(InvoiceCase, body.duplicate_of_case_id)
    if not original:
        raise HTTPException(status_code=422, detail=f"Original case '{body.duplicate_of_case_id}' ikke fundet")

    case.status = InvoiceCaseStatus.duplicate
    case.updated_at = datetime.utcnow()
    session.add(case)

    action_item = session.exec(
        select(InvoiceActionItem).where(
            InvoiceActionItem.invoice_case_id == case_id,
            InvoiceActionItem.active == True,  # noqa: E712
        )
    ).first()
    if action_item:
        action_item.status = InvoiceActionItemStatus.duplicate
        action_item.active = False
        action_item.updated_at = datetime.utcnow()
        session.add(action_item)

    audit.emit(session, case_id, InvoiceEventType.duplicate_detected,
               actor_type="user",
               payload={"duplicate_of_case_id": body.duplicate_of_case_id})
    session.commit()

    return {"id": case_id, "status": case.status.value, "duplicate_of": body.duplicate_of_case_id}


# ── 10. PATCH /invoice-monitoring/cases/{case_id}/fields ─────────────────────

@router.patch("/cases/{case_id}/fields")
def correct_field(case_id: str, body: FieldCorrectionRequest, ctx: CompanyContextDep) -> dict:
    """Manual correction of an extracted field. Creates a field_corrected audit event."""
    session = ctx.session
    case = _get_case_or_404(session, case_id)
    if case.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    allowed_fields = {
        "invoice_number", "amount_ore", "due_date", "invoice_date",
        "payment_reference", "creditor_name_raw",
    }
    if body.field_name not in allowed_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Feltet '{body.field_name}' kan ikke rettes. Tilladte felter: {sorted(allowed_fields)}",
        )

    old_value = str(getattr(case, body.field_name, None))

    if body.field_name == "amount_ore":
        try:
            setattr(case, body.field_name, int(body.new_value))
        except ValueError:
            raise HTTPException(status_code=422, detail="amount_ore skal være et heltal (øre)")
    elif body.field_name in ("due_date", "invoice_date"):
        try:
            from datetime import datetime as _dt
            parsed = _dt.strptime(body.new_value, "%Y-%m-%d").date()
            setattr(case, body.field_name, parsed)
        except ValueError:
            raise HTTPException(status_code=422, detail="Dato skal være YYYY-MM-DD")
    else:
        setattr(case, body.field_name, body.new_value)

    case.priority = compute_priority(
        due_date=case.due_date,
        is_reminder=case.is_reminder,
        creditor_id=case.creditor_id,
        confidence=case.confidence,
        amount_ore=case.amount_ore,
    )
    case.updated_at = datetime.utcnow()
    session.add(case)

    audit.emit(session, case_id, InvoiceEventType.field_corrected,
               actor_type="user",
               payload={
                   "field": body.field_name,
                   "old_value": old_value,
                   "new_value": body.new_value,
               })
    session.commit()

    return {"id": case_id, "field": body.field_name, "new_value": body.new_value}
