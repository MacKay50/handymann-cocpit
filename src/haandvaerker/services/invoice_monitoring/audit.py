"""InvoiceAuditService — append-only audit event creation.

Events are never mutated or deleted. Every important transition creates a record.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from sqlmodel import Session

from ...models.invoice_event import InvoiceEvent, InvoiceEventType


def emit(
    session: Session,
    invoice_case_id: str,
    event_type: InvoiceEventType,
    actor_type: str = "system",
    actor_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> InvoiceEvent:
    """Create and persist an audit event. Does NOT commit — caller commits."""
    event = InvoiceEvent(
        invoice_case_id=invoice_case_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        payload=json.dumps(payload) if payload else None,
    )
    session.add(event)
    return event
