"""Shared ingest layer for all three InboxMessage entry points.

Design contract (Phase 1):
- InboxMessage is ALWAYS created first, synchronously, as the primary artifact.
  It NEVER fails due to secondary steps.
- Secondary steps (auto-reply email) are wrapped in try/except that writes
  a human-readable context to InboxMessage.processing_error on failure.
  They never raise to the caller (Iron Law 2: fail loud but do not mask creation).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from ..models.inbox_message import InboxMessage, InboxSource
from .wizard_service import send_acknowledgement_email

logger = logging.getLogger(__name__)


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
) -> InboxMessage:
    """Create an InboxMessage and optionally send an acknowledgement email.

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

    if send_ack and sender_email:
        _run_secondary_send_ack(session, msg, company_name, company_id)

    return msg


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
