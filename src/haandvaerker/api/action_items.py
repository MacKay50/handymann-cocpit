from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.action_item import (
    ActionItem,
    ActionItemCreate,
    ActionItemRead,
    ActionItemStatus,
    ActionItemUpdate,
    VALID_ACTION_ITEM_TRANSITIONS,
)

router = APIRouter(prefix="/action-items", tags=["action-items"])


@router.post("/", response_model=ActionItemRead, status_code=201)
def create_action_item(
    data: ActionItemCreate, ctx: CompanyContextDep
) -> ActionItemRead:
    session = ctx.session
    now = datetime.utcnow()
    item = ActionItem(
        id=str(uuid.uuid4()),
        company_id=ctx.company_id,
        created_at=now,
        updated_at=now,
        **data.model_dump(),
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return ActionItemRead.model_validate(item)


@router.get("/", response_model=list[ActionItemRead])
def list_action_items(
    ctx: CompanyContextDep,
    project_id: Optional[str] = None,
    status: Optional[ActionItemStatus] = None,
    active_only: bool = True,
) -> list[ActionItemRead]:
    session = ctx.session
    stmt = select(ActionItem).where(ActionItem.company_id == ctx.company_id)
    if active_only:
        stmt = stmt.where(ActionItem.active == True)  # noqa: E712
    if project_id:
        stmt = stmt.where(ActionItem.project_id == project_id)
    if status:
        stmt = stmt.where(ActionItem.status == status)
    return [ActionItemRead.model_validate(i) for i in session.exec(stmt).all()]


@router.get("/{item_id}", response_model=ActionItemRead)
def get_action_item(item_id: str, ctx: CompanyContextDep) -> ActionItemRead:
    session = ctx.session
    item = session.get(ActionItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="ActionItem not found")
    if item.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return ActionItemRead.model_validate(item)


@router.patch("/{item_id}", response_model=ActionItemRead)
def update_action_item(
    item_id: str, data: ActionItemUpdate, ctx: CompanyContextDep
) -> ActionItemRead:
    session = ctx.session
    item = session.get(ActionItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="ActionItem not found")
    if item.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.updated_at = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return ActionItemRead.model_validate(item)


@router.post("/{item_id}/transition", response_model=ActionItemRead)
def transition_status(
    item_id: str, target_status: ActionItemStatus, ctx: CompanyContextDep
) -> ActionItemRead:
    session = ctx.session
    item = session.get(ActionItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="ActionItem not found")
    if item.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    allowed = VALID_ACTION_ITEM_TRANSITIONS.get(item.status.value, [])
    if target_status.value not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{item.status}' to '{target_status}'",
        )
    item.status = target_status
    item.updated_at = datetime.utcnow()
    session.add(item)
    session.commit()
    session.refresh(item)
    return ActionItemRead.model_validate(item)


@router.delete("/{item_id}", status_code=204)
def delete_action_item(item_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    item = session.get(ActionItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="ActionItem not found")
    if item.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    item.active = False
    session.add(item)
    session.commit()
