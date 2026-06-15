import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.enquiry import EnquiryRead
from ..models.inbox_message import (
    InboxMessage, InboxMessageConvert, InboxMessageCreate, InboxMessageRead,
    InboxSource, InboxStatus,
)
from ..services.inbox_ingest import create_enquiry_from_message

router = APIRouter(prefix="/inbox", tags=["inbox"])

VALID_TRANSITIONS: dict[InboxStatus, set[InboxStatus]] = {
    InboxStatus.unread: {InboxStatus.read, InboxStatus.archived, InboxStatus.converted},
    InboxStatus.read: {InboxStatus.converted, InboxStatus.archived, InboxStatus.unread},
    InboxStatus.archived: {InboxStatus.unread},
}


def _apply_transition(msg: InboxMessage, target: InboxStatus) -> None:
    allowed = VALID_TRANSITIONS.get(msg.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{msg.status}' to '{target}'",
        )
    msg.status = target


@router.get("/email-config-status", include_in_schema=False)
def email_config_status(ctx: CompanyContextDep) -> dict:
    from ..services.config_resolver import resolve_email_config
    cfg = resolve_email_config(ctx.session, ctx.company_id)
    return {"configured": cfg is not None}


@router.post("/fetch-email")
def fetch_email_inbox(ctx: CompanyContextDep) -> dict:
    from ..email_poller import poll_inbox, EmailConfigError
    from ..services.config_resolver import resolve_email_config
    session = ctx.session
    cfg = resolve_email_config(session, ctx.company_id)
    if cfg is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Email ikke konfigureret. "
                "Udfyld EMAIL_IMAP_HOST, EMAIL_USER og EMAIL_PASSWORD."
            ),
        )
    try:
        count = poll_inbox(ctx.company_id, session, cfg)
        return {"imported": count}
    except EmailConfigError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"IMAP-fejl: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"IMAP-fejl: {str(e)}")


@router.post("/", response_model=InboxMessageRead, status_code=201)
def create_message(data: InboxMessageCreate, ctx: CompanyContextDep) -> InboxMessageRead:
    session = ctx.session
    msg_id = data.id or str(uuid.uuid4())
    if session.get(InboxMessage, msg_id):
        raise HTTPException(status_code=409, detail=f"InboxMessage {msg_id} already exists")

    msg = InboxMessage(
        id=msg_id,
        company_id=ctx.company_id,
        received_at=data.received_at,
        source=data.source,
        sender_name=data.sender_name,
        sender_email=data.sender_email,
        sender_phone=data.sender_phone,
        subject=data.subject,
        body=data.body,
    )
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return InboxMessageRead.model_validate(msg)


@router.get("/", response_model=list[InboxMessageRead])
def list_messages(
    ctx: CompanyContextDep,
    active_only: bool = True,
    status: Optional[InboxStatus] = None,
    source: Optional[InboxSource] = None,
) -> list[InboxMessageRead]:
    session = ctx.session
    query = select(InboxMessage).where(InboxMessage.company_id == ctx.company_id)
    if active_only:
        query = query.where(InboxMessage.active == True)  # noqa: E712
    if status is not None:
        query = query.where(InboxMessage.status == status)
    if source is not None:
        query = query.where(InboxMessage.source == source)
    return [InboxMessageRead.model_validate(m) for m in session.exec(query).all()]


@router.get("/{message_id}", response_model=InboxMessageRead)
def get_message(message_id: str, ctx: CompanyContextDep) -> InboxMessageRead:
    session = ctx.session
    msg = session.get(InboxMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return InboxMessageRead.model_validate(msg)


@router.post("/{message_id}/read", response_model=InboxMessageRead)
def mark_read(message_id: str, ctx: CompanyContextDep) -> InboxMessageRead:
    session = ctx.session
    msg = session.get(InboxMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if msg.status == InboxStatus.read:
        return InboxMessageRead.model_validate(msg)
    _apply_transition(msg, InboxStatus.read)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return InboxMessageRead.model_validate(msg)


@router.post("/{message_id}/unread", response_model=InboxMessageRead)
def mark_unread(message_id: str, ctx: CompanyContextDep) -> InboxMessageRead:
    session = ctx.session
    msg = session.get(InboxMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _apply_transition(msg, InboxStatus.unread)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return InboxMessageRead.model_validate(msg)


@router.post("/{message_id}/archive", response_model=InboxMessageRead)
def archive_message(message_id: str, ctx: CompanyContextDep) -> InboxMessageRead:
    session = ctx.session
    msg = session.get(InboxMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _apply_transition(msg, InboxStatus.archived)
    session.add(msg)
    session.commit()
    session.refresh(msg)
    return InboxMessageRead.model_validate(msg)


@router.post("/{message_id}/convert", response_model=EnquiryRead, status_code=201)
def convert_to_enquiry(
    message_id: str, data: InboxMessageConvert, ctx: CompanyContextDep
) -> EnquiryRead:
    session = ctx.session
    msg = session.get(InboxMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    _apply_transition(msg, InboxStatus.converted)

    # Override title from the manual convert request; preserve original subject as notes
    original_subject = msg.subject
    msg.subject = data.title
    enquiry = create_enquiry_from_message(session, msg, ctx.company_id, notes=original_subject)
    msg.subject = original_subject

    msg.enquiry_id = enquiry.id
    session.add(msg)
    session.commit()
    session.refresh(enquiry)
    return EnquiryRead.model_validate(enquiry)


@router.post("/{message_id}/retry", response_model=InboxMessageRead)
def retry_secondary_steps(message_id: str, ctx: CompanyContextDep) -> InboxMessageRead:
    """Replay secondary steps (e.g. auto-reply email) for a message with processing_error.

    On success, processing_error is cleared.
    Returns the updated InboxMessage.
    """
    from ..services.inbox_ingest import replay_secondary_steps
    from ..models.company import Company

    session = ctx.session
    msg = session.get(InboxMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    company = session.get(Company, msg.company_id)
    if not company:
        raise HTTPException(status_code=500, detail="Firma ikke fundet for denne InboxMessage")
    company_name = company.name

    replay_secondary_steps(session=session, msg=msg, company_name=company_name)
    session.refresh(msg)
    return InboxMessageRead.model_validate(msg)


@router.delete("/{message_id}", status_code=204)
def delete_message(message_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    msg = session.get(InboxMessage, message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    msg.active = False
    session.add(msg)
    session.commit()
