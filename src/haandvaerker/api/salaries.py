import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select
from ..dependencies import CompanyContextDep
from ..models.employee import Employee
from ..models.salary import (
    Salary, SalaryCreate, SalaryRead, SalarySummary,
    SalaryStatus, SalaryUpdate, compute_salary_amounts,
)
from ..utils import to_decimal

router = APIRouter(prefix="/salaries", tags=["salaries"])


VALID_TRANSITIONS: dict[SalaryStatus, set[SalaryStatus]] = {
    SalaryStatus.draft: {SalaryStatus.approved, SalaryStatus.cancelled},
    SalaryStatus.approved: {SalaryStatus.paid},
}


def _require_active_employee(employee_id: str, session: Session) -> Employee:
    employee = session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' not found")
    if not employee.active:
        raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' is inactive")
    return employee


def _apply_transition(
    salary: Salary, target: SalaryStatus, session: Session
) -> SalaryRead:
    allowed = VALID_TRANSITIONS.get(salary.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{salary.status}' to '{target}'",
        )
    salary.status = target
    session.add(salary)
    session.commit()
    session.refresh(salary)
    return SalaryRead.model_validate(salary)


# /summary must be registered before /{salary_id}
@router.get("/summary", response_model=SalarySummary)
def get_summary(
    ctx: CompanyContextDep,
    employee_id: Optional[str] = None,
) -> SalarySummary:
    session = ctx.session
    if employee_id is not None:
        employee = session.get(Employee, employee_id)
        if not employee:
            raise HTTPException(status_code=422, detail=f"Employee '{employee_id}' not found")

    query = (
        select(Salary)
        .where(Salary.active == True)  # noqa: E712
        .where(Salary.status != SalaryStatus.cancelled)
        .where(Salary.company_id == ctx.company_id)
    )
    if employee_id is not None:
        query = query.where(Salary.employee_id == employee_id)

    rows = session.exec(query).all()
    q = Decimal("0.01")
    zero = Decimal("0")
    total_gross = float(
        sum((to_decimal(r.gross_amount) for r in rows), zero).quantize(q, ROUND_HALF_UP)
    )
    total_tax = float(
        sum((to_decimal(r.tax_amount) for r in rows), zero).quantize(q, ROUND_HALF_UP)
    )
    total_net = float(
        sum((to_decimal(r.net_amount) for r in rows), zero).quantize(q, ROUND_HALF_UP)
    )
    return SalarySummary(
        total_gross=total_gross,
        total_tax=total_tax,
        total_net=total_net,
        count=len(rows),
    )


@router.post("/", response_model=SalaryRead, status_code=201)
def create_salary(data: SalaryCreate, ctx: CompanyContextDep) -> SalaryRead:
    session = ctx.session
    employee = _require_active_employee(data.employee_id, session)
    if employee.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")

    if data.period_end < data.period_start:
        raise HTTPException(status_code=422, detail="period_end must be >= period_start")

    salary_id = data.id or str(uuid.uuid4())
    if session.get(Salary, salary_id):
        raise HTTPException(status_code=409, detail=f"Salary {salary_id} already exists")

    tax_amount, net_amount = compute_salary_amounts(data.gross_amount, data.tax_percentage)

    salary = Salary(
        id=salary_id,
        company_id=ctx.company_id,
        employee_id=data.employee_id,
        period_start=data.period_start,
        period_end=data.period_end,
        gross_amount=data.gross_amount,
        tax_percentage=data.tax_percentage,
        tax_amount=tax_amount,
        net_amount=net_amount,
        payment_date=data.payment_date,
        salary_ref=data.salary_ref,
        notes=data.notes,
    )
    session.add(salary)
    session.commit()
    session.refresh(salary)
    return SalaryRead.model_validate(salary)


@router.get("/", response_model=list[SalaryRead])
def list_salaries(
    ctx: CompanyContextDep,
    active_only: bool = True,
    employee_id: Optional[str] = None,
    status: Optional[SalaryStatus] = None,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
) -> list[SalaryRead]:
    session = ctx.session
    query = select(Salary).where(Salary.company_id == ctx.company_id)
    if active_only:
        query = query.where(Salary.active == True)  # noqa: E712
    if employee_id is not None:
        query = query.where(Salary.employee_id == employee_id)
    if status is not None:
        query = query.where(Salary.status == status)
    if period_from is not None:
        query = query.where(Salary.period_start >= period_from)
    if period_to is not None:
        query = query.where(Salary.period_start <= period_to)
    return [SalaryRead.model_validate(s) for s in session.exec(query).all()]


@router.get("/{salary_id}", response_model=SalaryRead)
def get_salary(salary_id: str, ctx: CompanyContextDep) -> SalaryRead:
    session = ctx.session
    salary = session.get(Salary, salary_id)
    if not salary:
        raise HTTPException(status_code=404, detail="Salary not found")
    if salary.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return SalaryRead.model_validate(salary)


@router.patch("/{salary_id}", response_model=SalaryRead)
def update_salary(salary_id: str, data: SalaryUpdate, ctx: CompanyContextDep) -> SalaryRead:
    session = ctx.session
    salary = session.get(Salary, salary_id)
    if not salary:
        raise HTTPException(status_code=404, detail="Salary not found")
    if salary.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    if salary.status != SalaryStatus.draft:
        raise HTTPException(status_code=409, detail="Can only edit draft salaries")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(salary, field, value)

    if salary.period_end < salary.period_start:
        raise HTTPException(status_code=422, detail="period_end must be >= period_start")

    salary.tax_amount, salary.net_amount = compute_salary_amounts(
        salary.gross_amount, salary.tax_percentage
    )

    session.add(salary)
    session.commit()
    session.refresh(salary)
    return SalaryRead.model_validate(salary)


@router.delete("/{salary_id}", status_code=204)
def deactivate_salary(salary_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    salary = session.get(Salary, salary_id)
    if not salary:
        raise HTTPException(status_code=404, detail="Salary not found")
    if salary.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    salary.active = False
    session.add(salary)
    session.commit()


@router.post("/{salary_id}/approve", response_model=SalaryRead)
def approve_salary(salary_id: str, ctx: CompanyContextDep) -> SalaryRead:
    session = ctx.session
    salary = session.get(Salary, salary_id)
    if not salary:
        raise HTTPException(status_code=404, detail="Salary not found")
    if salary.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(salary, SalaryStatus.approved, session)


@router.post("/{salary_id}/pay", response_model=SalaryRead)
def pay_salary(salary_id: str, ctx: CompanyContextDep) -> SalaryRead:
    session = ctx.session
    salary = session.get(Salary, salary_id)
    if not salary:
        raise HTTPException(status_code=404, detail="Salary not found")
    if salary.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(salary, SalaryStatus.paid, session)


@router.post("/{salary_id}/cancel", response_model=SalaryRead)
def cancel_salary(salary_id: str, ctx: CompanyContextDep) -> SalaryRead:
    session = ctx.session
    salary = session.get(Salary, salary_id)
    if not salary:
        raise HTTPException(status_code=404, detail="Salary not found")
    if salary.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return _apply_transition(salary, SalaryStatus.cancelled, session)
