import uuid
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.employee import Employee, EmployeeCreate, EmployeeRead, EmployeeUpdate

router = APIRouter(prefix="/employees", tags=["employees"])



@router.post("/", response_model=EmployeeRead, status_code=201)
def create_employee(data: EmployeeCreate, ctx: CompanyContextDep) -> EmployeeRead:
    session = ctx.session
    emp_id = data.id or str(uuid.uuid4())
    if session.get(Employee, emp_id):
        raise HTTPException(status_code=409, detail=f"Employee {emp_id} already exists")
    emp = Employee.model_validate({
        **data.model_dump(exclude={"id"}),
        "id": emp_id,
        "company_id": ctx.company_id,
    })
    session.add(emp)
    session.commit()
    session.refresh(emp)
    return EmployeeRead.from_orm_masked(emp)


@router.get("/", response_model=list[EmployeeRead])
def list_employees(
    ctx: CompanyContextDep,
    active_only: bool = True,
) -> list[EmployeeRead]:
    session = ctx.session
    query = select(Employee).where(Employee.company_id == ctx.company_id)
    if active_only:
        query = query.where(Employee.active == True)  # noqa: E712
    return [EmployeeRead.from_orm_masked(e) for e in session.exec(query).all()]


@router.get("/{employee_id}", response_model=EmployeeRead)
def get_employee(employee_id: str, ctx: CompanyContextDep) -> EmployeeRead:
    session = ctx.session
    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if emp.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    return EmployeeRead.from_orm_masked(emp)


@router.patch("/{employee_id}", response_model=EmployeeRead)
def update_employee(employee_id: str, data: EmployeeUpdate, ctx: CompanyContextDep) -> EmployeeRead:
    session = ctx.session
    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if emp.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(emp, field, value)
    session.add(emp)
    session.commit()
    session.refresh(emp)
    return EmployeeRead.from_orm_masked(emp)


@router.delete("/{employee_id}", status_code=204)
def deactivate_employee(employee_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    if emp.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    emp.active = False
    session.add(emp)
    session.commit()
