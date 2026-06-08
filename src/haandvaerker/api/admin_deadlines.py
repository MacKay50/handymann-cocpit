import calendar
import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.admin_deadline import (
    AdminDeadline, AdminDeadlineCreate, AdminDeadlineGenerateYear,
    AdminDeadlineRead, AdminDeadlineUpdate,
    DeadlineCategory, DeadlineStatus,
)

router = APIRouter(prefix="/admin-deadlines", tags=["admin-deadlines"])


VALID_TRANSITIONS: dict[DeadlineStatus, set[DeadlineStatus]] = {
    DeadlineStatus.pending: {DeadlineStatus.completed, DeadlineStatus.skipped},
    DeadlineStatus.completed: {DeadlineStatus.pending},
    DeadlineStatus.skipped: {DeadlineStatus.pending},
}


def _apply_transition(deadline: AdminDeadline, target: DeadlineStatus) -> None:
    allowed = VALID_TRANSITIONS.get(deadline.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{deadline.status}' to '{target}'",
        )
    deadline.status = target


def _generate_deadlines_for_year(
    company_id: str, year: int, categories: list[DeadlineCategory]
) -> list[tuple[str, DeadlineCategory, date]]:
    """Returns list of (title, category, due_date) tuples."""
    results = []

    if DeadlineCategory.vat_report in categories:
        quarters = [
            (f"Momsindberetning Q4 {year - 1}", date(year, 3, 1)),
            (f"Momsindberetning Q1 {year}", date(year, 6, 1)),
            (f"Momsindberetning Q2 {year}", date(year, 9, 1)),
            (f"Momsindberetning Q3 {year}", date(year, 12, 1)),
        ]
        for title, due in quarters:
            results.append((title, DeadlineCategory.vat_report, due))

    if DeadlineCategory.salary_run in categories:
        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            title = f"Lønsedler {date(year, month, 1).strftime('%B %Y')}"
            results.append((title, DeadlineCategory.salary_run, date(year, month, last_day)))

    if DeadlineCategory.annual_accounts in categories:
        results.append((
            f"Årsregnskab {year - 1}",
            DeadlineCategory.annual_accounts,
            date(year, 6, 30),
        ))

    if DeadlineCategory.corporate_tax in categories:
        results.append((
            f"Selskabsskat aconto {year} (1. rate)",
            DeadlineCategory.corporate_tax,
            date(year, 3, 20),
        ))
        results.append((
            f"Selskabsskat aconto {year} (2. rate)",
            DeadlineCategory.corporate_tax,
            date(year, 11, 20),
        ))

    if DeadlineCategory.insurance in categories:
        results.append((
            f"Forsikringsfornyelse {year}",
            DeadlineCategory.insurance,
            date(year, 1, 31),
        ))

    return results


# generate-year must be registered before /{deadline_id}
@router.post("/generate-year", response_model=list[AdminDeadlineRead], status_code=201)
def generate_year(data: AdminDeadlineGenerateYear, ctx: CompanyContextDep) -> list[AdminDeadlineRead]:
    session = ctx.session
    all_cats = list(DeadlineCategory)
    cats = data.categories if data.categories else all_cats

    templates = _generate_deadlines_for_year(ctx.company_id, data.year, cats)

    created = []
    for title, category, due_date in templates:
        existing = session.exec(
            select(AdminDeadline)
            .where(AdminDeadline.company_id == ctx.company_id)
            .where(AdminDeadline.category == category)
            .where(AdminDeadline.due_date == due_date)
            .where(AdminDeadline.active == True)  # noqa: E712
        ).first()
        if existing:
            created.append(AdminDeadlineRead.model_validate(existing))
            continue

        deadline = AdminDeadline(
            id=str(uuid.uuid4()),
            company_id=ctx.company_id,
            title=title,
            category=category,
            due_date=due_date,
        )
        session.add(deadline)
        session.flush()
        created.append(AdminDeadlineRead.model_validate(deadline))

    session.commit()
    return created


@router.post("/", response_model=AdminDeadlineRead, status_code=201)
def create_deadline(data: AdminDeadlineCreate, ctx: CompanyContextDep) -> AdminDeadlineRead:
    session = ctx.session
    deadline_id = data.id or str(uuid.uuid4())
    if session.get(AdminDeadline, deadline_id):
        raise HTTPException(status_code=409, detail=f"AdminDeadline {deadline_id} already exists")

    deadline = AdminDeadline(
        id=deadline_id,
        company_id=ctx.company_id,
        title=data.title,
        category=data.category,
        due_date=data.due_date,
        notes=data.notes,
    )
    session.add(deadline)
    session.commit()
    session.refresh(deadline)
    return AdminDeadlineRead.model_validate(deadline)


@router.get("/", response_model=list[AdminDeadlineRead])
def list_deadlines(
    ctx: CompanyContextDep,
    active_only: bool = True,
    category: Optional[DeadlineCategory] = None,
    status: Optional[DeadlineStatus] = None,
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
) -> list[AdminDeadlineRead]:
    session = ctx.session
    query = select(AdminDeadline).where(AdminDeadline.company_id == ctx.company_id)
    if active_only:
        query = query.where(AdminDeadline.active == True)  # noqa: E712
    if category is not None:
        query = query.where(AdminDeadline.category == category)
    if status is not None:
        query = query.where(AdminDeadline.status == status)
    if due_from is not None:
        query = query.where(AdminDeadline.due_date >= due_from)
    if due_to is not None:
        query = query.where(AdminDeadline.due_date <= due_to)
    return [AdminDeadlineRead.model_validate(d) for d in session.exec(query).all()]


@router.get("/{deadline_id}", response_model=AdminDeadlineRead)
def get_deadline(deadline_id: str, ctx: CompanyContextDep) -> AdminDeadlineRead:
    session = ctx.session
    deadline = session.get(AdminDeadline, deadline_id)
    if not deadline:
        raise HTTPException(status_code=404, detail="AdminDeadline not found")
    if deadline.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return AdminDeadlineRead.model_validate(deadline)


@router.patch("/{deadline_id}", response_model=AdminDeadlineRead)
def update_deadline(
    deadline_id: str, data: AdminDeadlineUpdate, ctx: CompanyContextDep
) -> AdminDeadlineRead:
    session = ctx.session
    deadline = session.get(AdminDeadline, deadline_id)
    if not deadline:
        raise HTTPException(status_code=404, detail="AdminDeadline not found")
    if deadline.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if deadline.status != DeadlineStatus.pending:
        raise HTTPException(status_code=409, detail="Can only edit pending deadlines")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(deadline, field, value)
    session.add(deadline)
    session.commit()
    session.refresh(deadline)
    return AdminDeadlineRead.model_validate(deadline)


@router.post("/{deadline_id}/complete", response_model=AdminDeadlineRead)
def complete_deadline(deadline_id: str, ctx: CompanyContextDep) -> AdminDeadlineRead:
    session = ctx.session
    deadline = session.get(AdminDeadline, deadline_id)
    if not deadline:
        raise HTTPException(status_code=404, detail="AdminDeadline not found")
    if deadline.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _apply_transition(deadline, DeadlineStatus.completed)
    session.add(deadline)
    session.commit()
    session.refresh(deadline)
    return AdminDeadlineRead.model_validate(deadline)


@router.post("/{deadline_id}/skip", response_model=AdminDeadlineRead)
def skip_deadline(deadline_id: str, ctx: CompanyContextDep) -> AdminDeadlineRead:
    session = ctx.session
    deadline = session.get(AdminDeadline, deadline_id)
    if not deadline:
        raise HTTPException(status_code=404, detail="AdminDeadline not found")
    if deadline.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _apply_transition(deadline, DeadlineStatus.skipped)
    session.add(deadline)
    session.commit()
    session.refresh(deadline)
    return AdminDeadlineRead.model_validate(deadline)


@router.post("/{deadline_id}/reopen", response_model=AdminDeadlineRead)
def reopen_deadline(deadline_id: str, ctx: CompanyContextDep) -> AdminDeadlineRead:
    session = ctx.session
    deadline = session.get(AdminDeadline, deadline_id)
    if not deadline:
        raise HTTPException(status_code=404, detail="AdminDeadline not found")
    if deadline.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _apply_transition(deadline, DeadlineStatus.pending)
    session.add(deadline)
    session.commit()
    session.refresh(deadline)
    return AdminDeadlineRead.model_validate(deadline)


@router.delete("/{deadline_id}", status_code=204)
def delete_deadline(deadline_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    deadline = session.get(AdminDeadline, deadline_id)
    if not deadline:
        raise HTTPException(status_code=404, detail="AdminDeadline not found")
    if deadline.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    deadline.active = False
    session.add(deadline)
    session.commit()
