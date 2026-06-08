import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.employee import Employee
from ..models.project import Project
from ..models.expense import (
    Expense, ExpenseCategory, ExpenseCreate, ExpenseRead,
    ExpenseSummary, ExpenseUpdate, compute_expense_amounts,
)
from ..utils import to_decimal

router = APIRouter(prefix="/expenses", tags=["expenses"])



def _require_active_project(project_id: str, session: Session) -> Project:
    project = session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' not found")
    if not project.active:
        raise HTTPException(status_code=422, detail=f"Project '{project_id}' is inactive")
    return project


def _require_active_employee(employee_id: str, session: Session) -> Employee:
    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' not found")
    if not emp.active:
        raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' is inactive")
    return emp


def _validate_create_inputs(data: ExpenseCreate) -> None:
    if data.category == ExpenseCategory.transport_km:
        if data.km is None:
            raise HTTPException(status_code=422, detail="km is required for transport_km category")
    else:
        if data.amount_excl_vat is None:
            raise HTTPException(
                status_code=422,
                detail=f"amount_excl_vat is required for {data.category} category",
            )


# summary must be registered before /{expense_id} to avoid routing conflict
@router.get("/summary", response_model=ExpenseSummary)
def get_summary(project_id: str, ctx: CompanyContextDep) -> ExpenseSummary:
    session = ctx.session
    project = _require_active_project(project_id, session)
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    entries = session.exec(
        select(Expense)
        .where(Expense.project_id == project_id)
        .where(Expense.active == True)  # noqa: E712
    ).all()

    q = Decimal("0.01")
    billable = [e for e in entries if e.billable]
    total_km = sum(
        to_decimal(e.km) for e in entries
        if e.category == ExpenseCategory.transport_km and e.km is not None
    )
    return ExpenseSummary(
        project_id=project_id,
        total_expenses=float(
            sum(to_decimal(e.amount_total) for e in entries).quantize(q, ROUND_HALF_UP)
        ),
        billable_expenses=float(
            sum(to_decimal(e.amount_total) for e in billable).quantize(q, ROUND_HALF_UP)
        ),
        total_km=float(total_km.quantize(q, ROUND_HALF_UP)),
    )


@router.post("/", response_model=ExpenseRead, status_code=201)
def create_expense(data: ExpenseCreate, ctx: CompanyContextDep) -> ExpenseRead:
    session = ctx.session
    project = _require_active_project(data.project_id, session)
    if project.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    _require_active_employee(data.employee_id, session)
    _validate_create_inputs(data)

    amount_excl_vat, vat_amount, amount_total, resolved_km, resolved_km_rate = (
        compute_expense_amounts(
            data.category, data.km, data.km_rate, data.amount_excl_vat, data.apply_vat
        )
    )

    expense = Expense(
        id=data.id or str(uuid.uuid4()),
        project_id=data.project_id,
        employee_id=data.employee_id,
        company_id=ctx.company_id,
        category=data.category,
        date=data.date,
        description=data.description,
        receipt_ref=data.receipt_ref,
        billable=data.billable,
        km=resolved_km,
        km_rate=resolved_km_rate,
        amount_excl_vat=amount_excl_vat,
        vat_amount=vat_amount,
        amount_total=amount_total,
    )
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return ExpenseRead.model_validate(expense)


@router.get("/", response_model=list[ExpenseRead])
def list_expenses(
    ctx: CompanyContextDep,
    active_only: bool = True,
    project_id: Optional[str] = None,
    employee_id: Optional[str] = None,
) -> list[ExpenseRead]:
    session = ctx.session
    query = select(Expense).where(Expense.company_id == ctx.company_id)
    if active_only:
        query = query.where(Expense.active == True)  # noqa: E712
    if project_id is not None:
        query = query.where(Expense.project_id == project_id)
    if employee_id is not None:
        query = query.where(Expense.employee_id == employee_id)
    return [ExpenseRead.model_validate(e) for e in session.exec(query).all()]


@router.get("/{expense_id}", response_model=ExpenseRead)
def get_expense(expense_id: str, ctx: CompanyContextDep) -> ExpenseRead:
    session = ctx.session
    expense = session.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if expense.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return ExpenseRead.model_validate(expense)


@router.patch("/{expense_id}", response_model=ExpenseRead)
def update_expense(expense_id: str, data: ExpenseUpdate, ctx: CompanyContextDep) -> ExpenseRead:
    session = ctx.session
    expense = session.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if expense.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(expense, field, value)
    session.add(expense)
    session.commit()
    session.refresh(expense)
    return ExpenseRead.model_validate(expense)


@router.delete("/{expense_id}", status_code=204)
def deactivate_expense(expense_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    expense = session.get(Expense, expense_id)
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found")
    if expense.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    expense.active = False
    session.add(expense)
    session.commit()
