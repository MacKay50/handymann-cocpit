from __future__ import annotations
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.inbox_message import InboxMessage
from ..models.message_classification import (
    ClassificationSource,
    MessageClassification,
    MessageClassificationRead,
    MessageClassificationUpdate,
    MessageEntity,
    MessageEntityRead,
)
from ..services.message_router import classify_message

router = APIRouter(prefix="/message-classifications", tags=["message-classifications"])


def _to_read(mc: MessageClassification, session: Session) -> MessageClassificationRead:
    entities = session.exec(
        select(MessageEntity).where(MessageEntity.classification_id == mc.id)
    ).all()
    try:
        secondary = json.loads(mc.secondary_categories_json) if mc.secondary_categories_json else []
    except (json.JSONDecodeError, TypeError):
        secondary = []
    return MessageClassificationRead(
        id=mc.id,
        company_id=mc.company_id,
        inbox_message_id=mc.inbox_message_id,
        primary_category=mc.primary_category,
        secondary_categories=secondary,
        is_quote_related=mc.is_quote_related,
        is_project_related=mc.is_project_related,
        is_calendar_related=mc.is_calendar_related,
        requires_action=mc.requires_action,
        priority=mc.priority,
        confidence=mc.confidence,
        classification_source=mc.classification_source,
        user_overridden=mc.user_overridden,
        active=mc.active,
        created_at=mc.created_at,
        updated_at=mc.updated_at,
        entities=[MessageEntityRead.model_validate(e) for e in entities],
    )


@router.post(
    "/classify/{inbox_message_id}",
    response_model=MessageClassificationRead,
    status_code=201,
)
def classify_inbox_message(
    inbox_message_id: str, ctx: CompanyContextDep
) -> MessageClassificationRead:
    """Classify an inbox message. Idempotent — returns existing if already classified."""
    session = ctx.session
    msg = session.get(InboxMessage, inbox_message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="InboxMessage not found")
    if msg.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    existing = session.exec(
        select(MessageClassification).where(
            MessageClassification.inbox_message_id == inbox_message_id,
            MessageClassification.active == True,  # noqa: E712
            MessageClassification.user_overridden == False,  # noqa: E712
        )
    ).first()
    if existing:
        return _to_read(existing, session)

    result = classify_message(
        subject=msg.subject,
        body=msg.body,
        sender_name=msg.sender_name,
        sender_email=msg.sender_email,
        sender_phone=msg.sender_phone,
    )

    now = datetime.utcnow()
    mc = MessageClassification(
        id=str(uuid.uuid4()),
        company_id=msg.company_id,
        inbox_message_id=inbox_message_id,
        primary_category=result.primary_category,
        secondary_categories_json=json.dumps(
            [c.value for c in result.secondary_categories], ensure_ascii=False
        ),
        is_quote_related=result.is_quote_related,
        is_project_related=result.is_project_related,
        is_calendar_related=result.is_calendar_related,
        requires_action=result.requires_action,
        priority=result.priority,
        confidence=result.confidence,
        classification_source=result.classification_source,
        created_at=now,
        updated_at=now,
    )
    session.add(mc)
    session.flush()

    for entity in result.entities:
        session.add(MessageEntity(
            id=str(uuid.uuid4()),
            classification_id=mc.id,
            entity_type=entity.entity_type,
            value=entity.value,
            normalized_value=entity.normalized_value,
            confidence=entity.confidence,
            created_at=now,
        ))

    session.commit()
    session.refresh(mc)
    return _to_read(mc, session)


@router.get("/", response_model=list[MessageClassificationRead])
def list_classifications(
    ctx: CompanyContextDep,
    active_only: bool = True,
) -> list[MessageClassificationRead]:
    session = ctx.session
    stmt = select(MessageClassification).where(
        MessageClassification.company_id == ctx.company_id
    )
    if active_only:
        stmt = stmt.where(MessageClassification.active == True)  # noqa: E712
    return [_to_read(mc, session) for mc in session.exec(stmt).all()]


@router.get("/{classification_id}", response_model=MessageClassificationRead)
def get_classification(
    classification_id: str, ctx: CompanyContextDep
) -> MessageClassificationRead:
    session = ctx.session
    mc = session.get(MessageClassification, classification_id)
    if not mc:
        raise HTTPException(status_code=404, detail="MessageClassification not found")
    if mc.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _to_read(mc, session)


@router.patch("/{classification_id}", response_model=MessageClassificationRead)
def override_classification(
    classification_id: str,
    data: MessageClassificationUpdate,
    ctx: CompanyContextDep,
) -> MessageClassificationRead:
    """Manual override — marks user_overridden=True and sets source=manual."""
    session = ctx.session
    mc = session.get(MessageClassification, classification_id)
    if not mc:
        raise HTTPException(status_code=404, detail="MessageClassification not found")
    if mc.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(mc, field, value)
    mc.user_overridden = True
    mc.classification_source = ClassificationSource.manual
    mc.updated_at = datetime.utcnow()
    session.add(mc)
    session.commit()
    session.refresh(mc)
    return _to_read(mc, session)
