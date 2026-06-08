from sqlmodel import SQLModel


class RevenueByPeriod(SQLModel):
    period: str
    invoice_count: int
    invoiced_amount: float
    paid_amount: float
    outstanding_amount: float


class ProjectProfitabilityRow(SQLModel):
    project_id: str
    project_title: str
    customer_name: str
    invoiced_total: float
    hours_cost: float
    expenses_cost: float
    gross_margin: float


class EmployeeHoursRow(SQLModel):
    employee_id: str
    employee_name: str
    total_hours: float
    billable_hours: float
    total_cost: float
    billable_cost: float


class TopCustomerRow(SQLModel):
    customer_id: str
    customer_name: str
    project_count: int
    invoiced_total: float
    paid_total: float


class ExpenseCategoryRow(SQLModel):
    category: str
    expense_count: int
    total_excl_vat: float
    total_vat: float
    total_amount: float
