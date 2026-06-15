"""Public unauthenticated enquiry endpoint.

POST /forespoergsel?company_id=<uuid>
  - Validates company_id against active companies.
  - Creates InboxMessage(source=website) via ingest_message.
  - Sends auto-reply acknowledgement (secondary step, never blocks creation).
  - Returns {"received": true, "acknowledged": bool} — NEVER leaks internal IDs.

GET /forespoergsel is served by main.py (static HTML).

Security:
  - Error response for unknown UUID and inactive company is identical (no leakage).
  - Timing-safe: both lookup failure and active=False return after the same code path.
  - company_id is NEVER echoed in the response.
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlmodel import Session

from ..database import get_session
from ..models.company import Company
from ..models.inbox_message import InboxSource
from ..services.inbox_ingest import ingest_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forespoergsel", tags=["forespoergsel"])

SessionDep = Annotated[Session, Depends(get_session)]

_INVALID_COMPANY = HTTPException(
    status_code=422,
    detail="Ugyldig eller inaktiv virksomhed.",
)


class EnquiryForm(BaseModel):
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    sender_phone: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None

    @field_validator("sender_name", "subject", mode="before")
    @classmethod
    def _strip(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip() or None
        return v


class EnquiryResponse(BaseModel):
    received: bool
    acknowledged: bool


@router.post("", response_model=EnquiryResponse, status_code=201)
def submit_enquiry(
    form: EnquiryForm,
    company_id: str,
    session: SessionDep,
) -> EnquiryResponse:
    """Accept a public enquiry for a known active company.

    Raises 422 with the same generic message for both unknown and inactive
    company_id values (no information leakage about UUID existence).
    """
    company = session.get(Company, company_id)
    if not company or not company.active:
        raise _INVALID_COMPANY

    msg = ingest_message(
        session=session,
        company_id=company.id,
        company_name=company.name,
        source=InboxSource.website,
        sender_name=form.sender_name,
        sender_email=form.sender_email,
        sender_phone=form.sender_phone,
        subject=form.subject,
        body=form.body,
        send_ack=bool(form.sender_email),
        classify=True,
    )

    acknowledged = msg.processing_error is None and bool(form.sender_email)

    logger.info(
        "Public enquiry received for company %s — InboxMessage %s created; ack=%s",
        company.id,
        msg.id,
        acknowledged,
    )

    return EnquiryResponse(received=True, acknowledged=acknowledged)
