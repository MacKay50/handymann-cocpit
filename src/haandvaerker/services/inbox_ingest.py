"""Shared ingest layer for all three InboxMessage entry points.

Design contract (Phase 1 + Phase 2):
- InboxMessage is ALWAYS created first, synchronously, as the primary artifact.
  It NEVER fails due to secondary steps.
- Secondary steps (auto-reply email, classification+Enquiry creation) are each
  wrapped in try/except that writes a human-readable context to
  InboxMessage.processing_error on failure.  They never raise to the caller
  (Iron Law 2: fail loud but do not mask creation).
- Classification is ALWAYS rule-based (use_llm=False by default).  Local AI
  enrichment is opt-in and is never used in the IMAP poll path.
- Enquiry auto-creation fires only for `new_quote_request` when the message
  does not already have an enquiry_id.  All other categories are left as inbox
  items only.
- Both this auto-creation path and the manual POST /inbox/{id}/convert endpoint
  delegate to `create_enquiry_from_message` — the single source of truth.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ..models.enquiry import Enquiry, EnquirySource, EnquiryStatus
from ..models.inbox_message import InboxMessage, InboxSource
from ..models.message_classification import (
    MessageCategory,
    MessageClassification,
    MessageEntity,
)
from .message_router import ClassificationResult, classify_message
from .wizard_service import send_acknowledgement_email

logger = logging.getLogger(__name__)


# ── Source mapping ────────────────────────────────────────────────────────────

_SOURCE_MAP: dict[InboxSource, EnquirySource] = {
    InboxSource.email: EnquirySource.email,
    InboxSource.phone: EnquirySource.phone,
    InboxSource.website: EnquirySource.website,
    InboxSource.walk_in: EnquirySource.walk_in,
    InboxSource.other: EnquirySource.other,
}


# ── Public helpers (also used by api/inbox.py) ────────────────────────────────

def inbox_source_to_enquiry_source(src: InboxSource) -> EnquirySource:
    """Map InboxSource enum to EnquirySource enum (exhaustive)."""
    return _SOURCE_MAP[src]


def create_enquiry_from_message(
    session: Session,
    msg: InboxMessage,
    company_id: str,
    notes: Optional[str] = None,
) -> Enquiry:
    """Create and persist an Enquiry from an InboxMessage.

    Sets title from msg.subject (truncated to 200 chars), contact fields from
    msg sender fields, source mapped from msg.source.  Does NOT commit —
    caller is responsible for commit.

    Used by both auto-creation (classify path) and manual convert endpoint.
    """
    title = (msg.subject or "Forespørgsel")[:200]
    enquiry = Enquiry(
        id=str(uuid.uuid4()),
        company_id=company_id,
        title=title,
        notes=notes,
        source=inbox_source_to_enquiry_source(msg.source),
        contact_name=msg.sender_name,
        contact_email=msg.sender_email,
        contact_phone=msg.sender_phone,
        status=EnquiryStatus.new,
    )
    session.add(enquiry)
    session.flush()
    return enquiry


# ── Public entry point ────────────────────────────────────────────────────────

def ingest_message(
    session: Session,
    company_id: str,
    company_name: str,
    source: InboxSource,
    sender_name: Optional[str] = None,
    sender_email: Optional[str] = None,
    sender_phone: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    received_at: Optional[datetime] = None,
    send_ack: bool = False,
    classify: bool = False,
    use_llm: bool = False,
) -> InboxMessage:
    """Create an InboxMessage and optionally classify it and send an acknowledgement.

    Args:
        session: DB session (already open, caller commits or this function does).
        company_id: Validated active company ID.
        company_name: Company display name (for email template).
        source: InboxSource enum value.
        sender_name: Sender display name.
        sender_email: Sender email address (required for send_ack).
        sender_phone: Sender phone number.
        subject: Message subject / enquiry topic.
        body: Message body text.
        received_at: Override creation timestamp; defaults to utcnow().
        send_ack: If True, attempt to send an auto-reply to sender_email.
        classify: If True, run rule-based classification and auto-create
            Enquiry for new_quote_request messages.
        use_llm: Passed to classify_message; True only for async enrichment
            flows, NEVER in the IMAP poll path.

    Returns:
        The persisted InboxMessage (always — even if secondary steps fail).
    """
    msg = InboxMessage(
        company_id=company_id,
        received_at=received_at or datetime.utcnow(),
        source=source,
        sender_name=sender_name,
        sender_email=sender_email,
        sender_phone=sender_phone,
        subject=subject,
        body=body,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)

    if classify:
        _run_secondary_classify(session, msg, use_llm=use_llm)

    if send_ack and sender_email:
        _run_secondary_send_ack(session, msg, company_name, company_id)

    return msg


# ── Secondary step: classify ──────────────────────────────────────────────────

def _run_secondary_classify(
    session: Session,
    msg: InboxMessage,
    *,
    use_llm: bool = False,
) -> None:
    """Classify msg and optionally auto-create an Enquiry.

    Never raises — all exceptions are caught and written to msg.processing_error.
    Idempotent: if MessageClassification already exists for this message, skips.
    """
    # Idempotency guard — skip if classification already done
    existing_cls = session.exec(
        select(MessageClassification).where(
            MessageClassification.inbox_message_id == msg.id
        )
    ).first()
    if existing_cls is not None:
        # Classification exists; still check if Enquiry creation is needed
        if (
            existing_cls.primary_category == MessageCategory.new_quote_request
            and msg.enquiry_id is None
        ):
            _auto_create_enquiry(session, msg)
        return

    try:
        result: ClassificationResult = classify_message(
            subject=msg.subject,
            body=msg.body,
            sender_name=msg.sender_name,
            sender_email=msg.sender_email,
            sender_phone=msg.sender_phone,
            use_llm=use_llm,
        )
    except Exception as exc:
        logger.warning(
            "Classification failed for InboxMessage %s: %s",
            msg.id,
            exc,
        )
        msg.processing_error = f"Klassificering fejlede: {exc}"
        session.add(msg)
        session.commit()
        return

    try:
        cls_record = MessageClassification(
            company_id=msg.company_id,
            inbox_message_id=msg.id,
            primary_category=result.primary_category,
            secondary_categories_json=json.dumps(
                [c.value for c in result.secondary_categories]
            ),
            is_quote_related=result.is_quote_related,
            is_project_related=result.is_project_related,
            is_calendar_related=result.is_calendar_related,
            requires_action=result.requires_action,
            priority=result.priority,
            confidence=result.confidence,
            classification_source=result.classification_source,
        )
        session.add(cls_record)
        session.flush()

        for entity in result.entities:
            session.add(
                MessageEntity(
                    classification_id=cls_record.id,
                    entity_type=entity.entity_type,
                    value=entity.value,
                    confidence=entity.confidence,
                )
            )
        session.flush()

        if (
            result.primary_category == MessageCategory.new_quote_request
            and msg.enquiry_id is None
        ):
            _auto_create_enquiry(session, msg)

        session.commit()

    except Exception as exc:
        session.rollback()
        logger.warning(
            "Persisting classification failed for InboxMessage %s: %s",
            msg.id,
            exc,
        )
        msg.enquiry_id = None  # REL-02: reset dangling FK after rollback
        msg.processing_error = f"Klassificering kunne ikke gemmes: {exc}"
        session.add(msg)
        session.commit()


def _auto_create_enquiry(session: Session, msg: InboxMessage) -> None:
    """Create an Enquiry linked to msg.  Idempotent: skips if enquiry_id already set.

    Caller is responsible for committing.
    """
    if msg.enquiry_id is not None:
        return
    enquiry = create_enquiry_from_message(session, msg, msg.company_id)
    msg.enquiry_id = enquiry.id
    session.add(msg)


# ── Secondary step: send acknowledgement ─────────────────────────────────────

def _run_secondary_send_ack(
    session: Session,
    msg: InboxMessage,
    company_name: str,
    company_id: str,
) -> None:
    """Send acknowledgement email; on any failure write to processing_error.

    Never raises — all exceptions are caught and written to msg.processing_error.
    """
    try:
        result = send_acknowledgement_email(
            to=msg.sender_email,  # type: ignore[arg-type]
            contact_name=msg.sender_name or "Kunde",
            company_name=company_name,
            session=session,
            company_id=company_id,
        )
        if not result.get("sent"):
            error_text = result.get("error") or "Afsendelse fejlede uden fejlbesked"
            msg.processing_error = f"Auto-svar ikke sendt: {error_text}"
            session.add(msg)
            session.commit()
    except Exception as exc:
        logger.warning(
            "Secondary step (send_ack) failed for InboxMessage %s: %s",
            msg.id,
            exc,
        )
        msg.processing_error = f"Auto-svar fejlede: {exc}"
        session.add(msg)
        session.commit()


def replay_secondary_steps(
    session: Session,
    msg: InboxMessage,
    company_name: str,
) -> bool:
    """Replay secondary steps for a message with processing_error.

    Returns True if all secondary steps succeeded and processing_error was cleared.
    Writes to processing_error on failure. Never raises.
    """
    if msg.sender_email:
        try:
            result = send_acknowledgement_email(
                to=msg.sender_email,
                contact_name=msg.sender_name or "Kunde",
                company_name=company_name,
                session=session,
                company_id=msg.company_id,
            )
            if result.get("sent"):
                msg.processing_error = None
                session.add(msg)
                session.commit()
                return True
            else:
                error_text = result.get("error") or "Afsendelse fejlede uden fejlbesked"
                msg.processing_error = f"Auto-svar ikke sendt: {error_text}"
                session.add(msg)
                session.commit()
                return False
        except Exception as exc:
            logger.warning(
                "Replay secondary steps failed for InboxMessage %s: %s",
                msg.id,
                exc,
            )
            msg.processing_error = f"Auto-svar fejlede: {exc}"
            session.add(msg)
            session.commit()
            return False
    else:
        # No email to send — clear the error (nothing to retry)
        msg.processing_error = None
        session.add(msg)
        session.commit()
        return True
