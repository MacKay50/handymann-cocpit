"""InvoiceMonitoringService — orchestrates the full ingestion pipeline.

Pipeline:
  1. Create InvoiceDocument (from message body text)
  2. Classify document → if not relevant, emit event + return early
  3. Extract fields
  4. Match or create creditor
  5. Compute fingerprint → check for duplicate/reminder
  6. Create InvoiceCase
  7. Create ExtractionEvidence
  8. Compute priority
  9. Create InvoiceActionItem (one per case)
 10. Emit audit events throughout

Public surface:
  ingest_from_inbox(session, inbox_message, company_id) → InvoiceCase
      Core pipeline.  Does NOT commit — caller commits.
      Idempotent: returns existing InvoiceCase if source_inbox_message_id
      already present.

  ingest_sample(session, company_id, subject, sender, body_text, ...) → IngestResult
      Thin dev/test wrapper.  Creates a MailMessage, delegates to
      ingest_from_inbox, and commits.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlmodel import Session, select

from ...models.extraction_evidence import ExtractionEvidence
from ...models.invoice_action_item import InvoiceActionItem, InvoiceActionItemStatus
from ...models.invoice_case import InvoiceCase, InvoiceCaseStatus
from ...models.invoice_document import InvoiceDocument, InvoiceDocumentType, OcrStatus
from ...models.invoice_event import InvoiceEventType
from ...models.mail_message import MailMessage, MailProcessingStatus
from . import audit
from .classifier import classify
from .creditor_matching import match_or_create
from .duplicate import compute_fingerprint, find_existing_case, handle_reminder_on_existing
from .extractor import extract
from .priority import compute_priority

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    mail_message_id: str
    invoice_case_id: Optional[str]
    action_item_id: Optional[str]
    is_relevant: bool
    is_duplicate: bool
    is_reminder: bool
    priority: Optional[str]
    status: str


# ── Core pipeline ─────────────────────────────────────────────────────────────

def ingest_from_inbox(
    session: Session,
    inbox_message: "MailMessage | object",  # InboxMessage or MailMessage duck-type
    company_id: str,
    *,
    _override_creditor_name: Optional[str] = None,
    _override_invoice_number: Optional[str] = None,
    _override_amount_ore: Optional[int] = None,
    _override_due_date: Optional[date] = None,
) -> InvoiceCase:
    """Run the full invoice ingestion pipeline for a single message.

    Idempotent: if an InvoiceCase with source_inbox_message_id equal to
    inbox_message.id already exists, it is returned immediately without
    re-running the pipeline.

    Does NOT commit — caller is responsible for committing the session.

    Args:
        session:        Open SQLModel Session.
        inbox_message:  Any object with .id, .subject, .body/.body_text,
                        and .sender_email/.sender attributes.
        company_id:     Validated active company ID (multi-tenant key).
        _override_*:    Extraction overrides for the dev/sample endpoint.
                        Not used in the normal inbox routing path.

    Returns:
        The existing or newly-created InvoiceCase.

    Raises:
        Only on programming errors (e.g. bad enum value).  External I/O
        failures (e.g. DB constraint) propagate — caller wraps if needed.
    """
    msg_id: str = inbox_message.id  # type: ignore[union-attr]

    # ── Idempotency check ─────────────────────────────────────────────────────
    existing_case = session.exec(
        select(InvoiceCase).where(
            InvoiceCase.source_inbox_message_id == msg_id,
            InvoiceCase.company_id == company_id,
        )
    ).first()
    if existing_case is not None:
        return existing_case

    # ── Resolve text fields from duck-typed message ───────────────────────────
    subject: str = getattr(inbox_message, "subject", "") or ""
    # InboxMessage uses .body; MailMessage uses .body_text
    body_text: str = (
        getattr(inbox_message, "body_text", None)
        or getattr(inbox_message, "body", None)
        or ""
    )
    sender: str = (
        getattr(inbox_message, "sender_email", None)
        or getattr(inbox_message, "sender", None)
        or ""
    )

    # ── 1. InvoiceDocument ────────────────────────────────────────────────────
    # For InboxMessage sources we do not have a MailMessage FK — use None.
    mail_message_id: Optional[str] = getattr(inbox_message, "_mail_message_id", None)

    doc = InvoiceDocument(
        company_id=company_id,
        mail_message_id=mail_message_id,
        filename="inbox.txt",
        text_content=body_text,
        ocr_status=OcrStatus.not_needed,
    )
    session.add(doc)
    session.flush()

    # ── 2. Classify ───────────────────────────────────────────────────────────
    classification = classify(subject=subject, body_text=body_text)

    doc.document_type = (
        InvoiceDocumentType(classification.document_type)
        if classification.document_type in InvoiceDocumentType._value2member_map_
        else InvoiceDocumentType.unknown
    )
    session.add(doc)

    if not classification.is_payment_relevant:
        fp = compute_fingerprint(None, None, 0, "DKK", None, None)
        case = InvoiceCase(
            company_id=company_id,
            source_inbox_message_id=msg_id,
            source_document_id=doc.id,
            amount_ore=0,
            fingerprint=fp,
            status=InvoiceCaseStatus.not_relevant,
            confidence=classification.confidence,
        )
        session.add(case)
        session.flush()
        audit.emit(
            session, case.id, InvoiceEventType.document_classified,
            payload={"is_relevant": False, "reason": classification.reason},
        )
        return case

    # ── 3. Extract fields ─────────────────────────────────────────────────────
    extraction = extract(text=body_text, subject=subject, sender=sender)

    # Caller-supplied overrides take precedence (used by dev/sample endpoint only).
    final_creditor_name = _override_creditor_name or extraction.creditor_name
    final_invoice_number = _override_invoice_number or extraction.invoice_number
    final_amount_ore = (
        _override_amount_ore if _override_amount_ore is not None
        else (extraction.amount_ore or 0)
    )
    final_due_date = _override_due_date or extraction.due_date
    final_confidence = extraction.confidence

    # ── 4. Match/create creditor ──────────────────────────────────────────────
    matched_creditor_id: Optional[str] = None
    if final_creditor_name:
        creditor, _ = match_or_create(session, company_id, final_creditor_name)
        matched_creditor_id = creditor.id

    # ── 5. Fingerprint / duplicate check ─────────────────────────────────────
    fp = compute_fingerprint(
        final_creditor_name,
        final_invoice_number,
        final_amount_ore,
        "DKK",
        final_due_date,
        extraction.payment_reference,
    )
    existing_fp = find_existing_case(session, company_id, fp)

    if existing_fp:
        if extraction.is_reminder or classification.document_type == "reminder":
            handle_reminder_on_existing(session, existing_fp, extraction.reminder_level)
            audit.emit(
                session, existing_fp.id, InvoiceEventType.reminder_received,
                payload={"reminder_level": extraction.reminder_level, "subject": subject},
            )
            # Return the existing case — still link the inbox message if unset
            if existing_fp.source_inbox_message_id is None:
                existing_fp.source_inbox_message_id = msg_id
                session.add(existing_fp)
            return existing_fp
        else:
            # True duplicate — create a dup case scoped to this inbox message
            fp_unique = fp + f"_dup_{msg_id[:8]}"
            dup_case = InvoiceCase(
                company_id=company_id,
                creditor_id=matched_creditor_id,
                source_inbox_message_id=msg_id,
                source_document_id=doc.id,
                invoice_number=final_invoice_number,
                amount_ore=final_amount_ore,
                due_date=final_due_date,
                fingerprint=fp_unique,
                status=InvoiceCaseStatus.duplicate,
                confidence=final_confidence,
                creditor_name_raw=final_creditor_name,
            )
            session.add(dup_case)
            session.flush()
            audit.emit(
                session, dup_case.id, InvoiceEventType.duplicate_detected,
                payload={"original_case_id": existing_fp.id},
            )
            return dup_case

    # ── 6. Create InvoiceCase ─────────────────────────────────────────────────
    is_reminder = extraction.is_reminder or classification.document_type == "reminder"
    priority = compute_priority(
        due_date=final_due_date,
        is_reminder=is_reminder,
        creditor_id=matched_creditor_id,
        confidence=final_confidence,
        amount_ore=final_amount_ore,
    )
    initial_status = (
        InvoiceCaseStatus.reminder_received if is_reminder
        else InvoiceCaseStatus.payment_required
    )
    case = InvoiceCase(
        company_id=company_id,
        creditor_id=matched_creditor_id,
        source_inbox_message_id=msg_id,
        source_document_id=doc.id,
        invoice_number=final_invoice_number,
        amount_ore=final_amount_ore,
        invoice_date=extraction.invoice_date,
        due_date=final_due_date,
        payment_reference=extraction.payment_reference,
        status=initial_status,
        priority=priority,
        confidence=final_confidence,
        fingerprint=fp,
        is_reminder=is_reminder,
        reminder_level=extraction.reminder_level,
        creditor_name_raw=final_creditor_name,
    )
    session.add(case)
    session.flush()

    # ── 7. ExtractionEvidence ─────────────────────────────────────────────────
    for ev in extraction.evidence:
        session.add(ExtractionEvidence(
            invoice_case_id=case.id,
            field_name=ev.field_name,
            extracted_value=ev.extracted_value,
            source_text=ev.source_text,
            confidence=ev.confidence,
        ))

    # ── 8. Audit events ───────────────────────────────────────────────────────
    audit.emit(session, case.id, InvoiceEventType.mail_received,
               payload={"subject": subject, "sender": sender})
    audit.emit(session, case.id, InvoiceEventType.document_classified,
               payload={"document_type": classification.document_type,
                        "confidence": classification.confidence})
    audit.emit(session, case.id, InvoiceEventType.invoice_fields_extracted,
               payload={"confidence": final_confidence,
                        "invoice_number": final_invoice_number,
                        "amount_ore": final_amount_ore})
    if matched_creditor_id:
        audit.emit(session, case.id, InvoiceEventType.creditor_matched,
                   payload={"creditor_id": matched_creditor_id,
                            "creditor_name": final_creditor_name})
    audit.emit(session, case.id, InvoiceEventType.invoice_case_created,
               payload={"status": initial_status.value, "priority": priority.value})

    # ── 9. ActionItem ─────────────────────────────────────────────────────────
    action_item = InvoiceActionItem(
        invoice_case_id=case.id,
        company_id=company_id,
        status=InvoiceActionItemStatus.open,
        due_date=final_due_date,
    )
    session.add(action_item)
    session.flush()
    audit.emit(session, case.id, InvoiceEventType.action_item_created,
               payload={"action_item_id": action_item.id})

    return case


# ── Dev/sample wrapper ────────────────────────────────────────────────────────

def ingest_sample(
    session: Session,
    company_id: str,
    subject: str,
    sender: str,
    body_text: str,
    amount_ore: Optional[int] = None,
    invoice_number: Optional[str] = None,
    due_date: Optional[date] = None,
    creditor_name: Optional[str] = None,
) -> IngestResult:
    """Ingest a mail + optional field hints. Used by dev/sample endpoint and tests.

    Creates a MailMessage, delegates the full pipeline to ingest_from_inbox,
    and commits.  This is a thin wrapper — all pipeline logic lives in
    ingest_from_inbox.
    """
    # ── 1. MailMessage ────────────────────────────────────────────────────────
    body_hash = hashlib.sha256((body_text or "").encode()).hexdigest()
    mail = MailMessage(
        company_id=company_id,
        subject=subject,
        sender=sender,
        body_text=body_text,
        body_hash=body_hash,
        processing_status=MailProcessingStatus.processing,
    )
    session.add(mail)
    session.flush()

    # Attach the mail_message_id so ingest_from_inbox can link InvoiceDocument
    mail._mail_message_id = mail.id

    # ── 2. Delegate to ingest_from_inbox (passing caller hints as overrides) ──
    case = ingest_from_inbox(
        session, mail, company_id,
        _override_creditor_name=creditor_name,
        _override_invoice_number=invoice_number,
        _override_amount_ore=amount_ore,
        _override_due_date=due_date,
    )

    # ── 3. Resolve action item for return value ───────────────────────────────
    action_item = session.exec(
        select(InvoiceActionItem).where(InvoiceActionItem.invoice_case_id == case.id)
    ).first()

    # ── 4. Update mail status and commit ─────────────────────────────────────
    mail.processing_status = MailProcessingStatus.processed
    session.add(mail)
    session.commit()

    # ── 5. Build IngestResult ─────────────────────────────────────────────────
    is_relevant = case.status != InvoiceCaseStatus.not_relevant
    is_duplicate = case.status == InvoiceCaseStatus.duplicate
    is_reminder = case.is_reminder

    if not is_relevant:
        return IngestResult(
            mail_message_id=mail.id,
            invoice_case_id=case.id,
            action_item_id=None,
            is_relevant=False,
            is_duplicate=False,
            is_reminder=False,
            priority=None,
            status="not_relevant",
        )

    return IngestResult(
        mail_message_id=mail.id,
        invoice_case_id=case.id,
        action_item_id=action_item.id if action_item else None,
        is_relevant=True,
        is_duplicate=is_duplicate,
        is_reminder=is_reminder,
        priority=case.priority.value if case.priority else None,
        status=case.status.value,
    )
