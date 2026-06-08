"""InvoiceMonitoringService — orchestrates the full ingestion pipeline.

Pipeline:
  1. Create MailMessage
  2. Create InvoiceDocument (if attachment text provided)
  3. Classify document → if not relevant, emit event + return early
  4. Extract fields
  5. Match or create creditor
  6. Compute fingerprint → check for duplicate/reminder
  7. Create InvoiceCase
  8. Create ExtractionEvidence
  9. Compute priority
 10. Create InvoiceActionItem (one per case)
 11. Emit audit events throughout
 12. Commit
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlmodel import Session

from ...models.extraction_evidence import ExtractionEvidence
from ...models.invoice_action_item import InvoiceActionItem, InvoiceActionItemStatus
from ...models.invoice_case import InvoiceCase, InvoiceCaseStatus
from ...models.invoice_document import InvoiceDocument, InvoiceDocumentType, OcrStatus
from ...models.mail_message import MailMessage, MailProcessingStatus
from ...models.invoice_event import InvoiceEventType
from . import audit
from .classifier import classify
from .creditor_matching import match_or_create
from .duplicate import compute_fingerprint, find_existing_case, handle_reminder_on_existing
from .extractor import extract
from .priority import compute_priority


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
    """Ingest a mail + optional field hints. Used by dev/sample endpoint and tests."""

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

    # ── 2. InvoiceDocument ────────────────────────────────────────────────────
    doc = InvoiceDocument(
        company_id=company_id,
        mail_message_id=mail.id,
        filename="sample.txt",
        text_content=body_text,
        ocr_status=OcrStatus.not_needed,
    )
    session.add(doc)
    session.flush()

    # ── 3. Classify ───────────────────────────────────────────────────────────
    classification = classify(subject=subject, body_text=body_text or "")

    doc.document_type = InvoiceDocumentType(classification.document_type) if classification.document_type in InvoiceDocumentType._value2member_map_ else InvoiceDocumentType.unknown
    session.add(doc)

    if not classification.is_payment_relevant:
        mail.processing_status = MailProcessingStatus.processed
        session.add(mail)
        # Create a minimal not_relevant case so there's an audit trail
        fp = compute_fingerprint(creditor_name, invoice_number, amount_ore or 0, "DKK", due_date, None)
        case = InvoiceCase(
            company_id=company_id,
            source_mail_message_id=mail.id,
            source_document_id=doc.id,
            amount_ore=0,
            fingerprint=fp,
            status=InvoiceCaseStatus.not_relevant,
            confidence=classification.confidence,
        )
        session.add(case)
        session.flush()
        audit.emit(session, case.id, InvoiceEventType.document_classified,
                   payload={"is_relevant": False, "reason": classification.reason})
        session.commit()
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

    # ── 4. Extract fields ─────────────────────────────────────────────────────
    extraction = extract(text=body_text or "", subject=subject, sender=sender)

    # Caller-supplied hints override extractor
    final_creditor_name = creditor_name or extraction.creditor_name
    final_invoice_number = invoice_number or extraction.invoice_number
    final_amount_ore = amount_ore if amount_ore is not None else (extraction.amount_ore or 0)
    final_due_date = due_date or extraction.due_date
    final_confidence = extraction.confidence

    # ── 5. Match/create creditor ──────────────────────────────────────────────
    matched_creditor_id: Optional[str] = None
    if final_creditor_name:
        creditor, _ = match_or_create(session, company_id, final_creditor_name)
        matched_creditor_id = creditor.id

    # ── 6. Fingerprint / duplicate check ─────────────────────────────────────
    fp = compute_fingerprint(
        final_creditor_name,
        final_invoice_number,
        final_amount_ore,
        "DKK",
        final_due_date,
        extraction.payment_reference,
    )
    existing = find_existing_case(session, company_id, fp)

    if existing:
        if extraction.is_reminder or classification.document_type == "reminder":
            # Reminder on existing case — raise priority, do not create duplicate action
            handle_reminder_on_existing(session, existing, extraction.reminder_level)
            audit.emit(session, existing.id, InvoiceEventType.reminder_received,
                       payload={"reminder_level": extraction.reminder_level,
                                "subject": subject})
            mail.processing_status = MailProcessingStatus.processed
            session.add(mail)
            session.commit()
            return IngestResult(
                mail_message_id=mail.id,
                invoice_case_id=existing.id,
                action_item_id=None,
                is_relevant=True,
                is_duplicate=False,
                is_reminder=True,
                priority=existing.priority.value,
                status="reminder_on_existing",
            )
        else:
            # True duplicate
            fp_unique = fp + f"_dup_{mail.id[:8]}"
            dup_case = InvoiceCase(
                company_id=company_id,
                creditor_id=matched_creditor_id,
                source_mail_message_id=mail.id,
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
            audit.emit(session, dup_case.id, InvoiceEventType.duplicate_detected,
                       payload={"original_case_id": existing.id})
            mail.processing_status = MailProcessingStatus.processed
            session.add(mail)
            session.commit()
            return IngestResult(
                mail_message_id=mail.id,
                invoice_case_id=dup_case.id,
                action_item_id=None,
                is_relevant=True,
                is_duplicate=True,
                is_reminder=False,
                priority=None,
                status="duplicate",
            )

    # ── 7. Create InvoiceCase ─────────────────────────────────────────────────
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
        source_mail_message_id=mail.id,
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

    # ── 8. ExtractionEvidence ─────────────────────────────────────────────────
    for ev in extraction.evidence:
        session.add(ExtractionEvidence(
            invoice_case_id=case.id,
            field_name=ev.field_name,
            extracted_value=ev.extracted_value,
            source_text=ev.source_text,
            confidence=ev.confidence,
        ))

    # ── 9. Audit events ───────────────────────────────────────────────────────
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

    # ── 10. ActionItem ────────────────────────────────────────────────────────
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

    mail.processing_status = MailProcessingStatus.processed
    session.add(mail)
    session.commit()

    return IngestResult(
        mail_message_id=mail.id,
        invoice_case_id=case.id,
        action_item_id=action_item.id,
        is_relevant=True,
        is_duplicate=False,
        is_reminder=is_reminder,
        priority=priority.value,
        status=initial_status.value,
    )
