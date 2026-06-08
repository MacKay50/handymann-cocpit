from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional, Union

from fastapi import APIRouter
from fastapi.responses import Response
from sqlmodel import select

from ..dependencies import CompanyContextDep
from ..models.customer import Customer
from ..models.employee import Employee
from ..models.expense import Expense
from ..models.invoice import Invoice, InvoiceStatus
from ..models.project import Project
from ..models.reports import (
    EmployeeHoursRow,
    ExpenseCategoryRow,
    ProjectProfitabilityRow,
    RevenueByPeriod,
    TopCustomerRow,
)
from ..models.time_entry import TimeEntry
from ..utils import to_decimal

router = APIRouter(prefix="/reports", tags=["reports"])


Q = Decimal("0.01")
ZERO = Decimal("0")

_ACTIVE_INVOICE_STATUSES = {InvoiceStatus.sent, InvoiceStatus.paid}

_REVENUE_FIELDS = ["period", "invoice_count", "invoiced_amount", "paid_amount", "outstanding_amount"]
_PROFITABILITY_FIELDS = ["project_id", "project_title", "customer_name", "invoiced_total", "hours_cost", "expenses_cost", "gross_margin"]
_EMPLOYEE_HOURS_FIELDS = ["employee_id", "employee_name", "total_hours", "billable_hours", "total_cost", "billable_cost"]
_TOP_CUSTOMERS_FIELDS = ["customer_id", "customer_name", "project_count", "invoiced_total", "paid_total"]
_EXPENSE_BREAKDOWN_FIELDS = ["category", "expense_count", "total_excl_vat", "total_vat", "total_amount"]


def _to_csv(rows: list, fields: list[str], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row.model_dump())
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _quarter(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def _month(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


# ── Revenue ───────────────────────────────────────────────────────────────────

@router.get("/revenue", response_model=list[RevenueByPeriod])
def report_revenue(
    ctx: CompanyContextDep,
    year: int,
    group_by: Literal["month", "quarter", "year"] = "month",
    format: Optional[Literal["json", "csv"]] = "json",
) -> Union[list[RevenueByPeriod], Response]:
    session = ctx.session
    company_id = ctx.company_id

    invoices = session.exec(
        select(Invoice)
        .where(Invoice.company_id == company_id)
        .where(Invoice.status != InvoiceStatus.draft)
        .where(Invoice.status != InvoiceStatus.cancelled)
        .where(Invoice.issue_date >= date(year, 1, 1))
        .where(Invoice.issue_date <= date(year, 12, 31))
    ).all()

    buckets: dict[str, dict] = defaultdict(lambda: {
        "invoice_count": 0,
        "invoiced_amount": ZERO,
        "paid_amount": ZERO,
    })

    for inv in invoices:
        if group_by == "month":
            key = _month(inv.issue_date)
        elif group_by == "quarter":
            key = _quarter(inv.issue_date)
        else:
            key = str(inv.issue_date.year)

        b = buckets[key]
        b["invoice_count"] += 1
        b["invoiced_amount"] += to_decimal(inv.total)
        if inv.status == InvoiceStatus.paid:
            b["paid_amount"] += to_decimal(inv.total)

    result = []
    for period, b in sorted(buckets.items()):
        invoiced = b["invoiced_amount"].quantize(Q, ROUND_HALF_UP)
        paid = b["paid_amount"].quantize(Q, ROUND_HALF_UP)
        outstanding = (invoiced - paid).quantize(Q, ROUND_HALF_UP)
        result.append(RevenueByPeriod(
            period=period,
            invoice_count=b["invoice_count"],
            invoiced_amount=float(invoiced),
            paid_amount=float(paid),
            outstanding_amount=float(outstanding),
        ))
    if format == "csv":
        return _to_csv(result, _REVENUE_FIELDS, f"revenue-{year}.csv")
    return result


# ── Project profitability ─────────────────────────────────────────────────────

@router.get("/project-profitability", response_model=list[ProjectProfitabilityRow])
def report_project_profitability(
    ctx: CompanyContextDep,
    format: Optional[Literal["json", "csv"]] = "json",
) -> Union[list[ProjectProfitabilityRow], Response]:
    session = ctx.session
    company_id = ctx.company_id

    projects = session.exec(
        select(Project)
        .where(Project.company_id == company_id)
        .where(Project.active == True)  # noqa: E712
    ).all()

    result = []
    for project in projects:
        customer = session.get(Customer, project.customer_id)
        customer_name = customer.name if customer else ""

        invoices = session.exec(
            select(Invoice)
            .where(Invoice.project_id == project.id)
            .where(Invoice.status != InvoiceStatus.draft)
            .where(Invoice.status != InvoiceStatus.cancelled)
        ).all()
        invoiced_total = sum((to_decimal(inv.total) for inv in invoices), ZERO)

        time_entries = session.exec(
            select(TimeEntry)
            .where(TimeEntry.project_id == project.id)
            .where(TimeEntry.active == True)  # noqa: E712
        ).all()
        hours_cost = sum((to_decimal(te.total) for te in time_entries), ZERO)

        expenses = session.exec(
            select(Expense)
            .where(Expense.project_id == project.id)
            .where(Expense.active == True)  # noqa: E712
        ).all()
        expenses_cost = sum((to_decimal(exp.amount_total) for exp in expenses), ZERO)

        invoiced_q = invoiced_total.quantize(Q, ROUND_HALF_UP)
        hours_q = hours_cost.quantize(Q, ROUND_HALF_UP)
        expenses_q = expenses_cost.quantize(Q, ROUND_HALF_UP)
        margin = (invoiced_q - hours_q - expenses_q).quantize(Q, ROUND_HALF_UP)

        result.append(ProjectProfitabilityRow(
            project_id=project.id,
            project_title=project.title,
            customer_name=customer_name,
            invoiced_total=float(invoiced_q),
            hours_cost=float(hours_q),
            expenses_cost=float(expenses_q),
            gross_margin=float(margin),
        ))
    if format == "csv":
        return _to_csv(result, _PROFITABILITY_FIELDS, "project-profitability.csv")
    return result


# ── Employee hours ────────────────────────────────────────────────────────────

@router.get("/employee-hours", response_model=list[EmployeeHoursRow])
def report_employee_hours(
    ctx: CompanyContextDep,
    from_date: date,
    to_date: date,
    format: Optional[Literal["json", "csv"]] = "json",
) -> Union[list[EmployeeHoursRow], Response]:
    session = ctx.session
    company_id = ctx.company_id

    entries = session.exec(
        select(TimeEntry)
        .where(TimeEntry.company_id == company_id)
        .where(TimeEntry.active == True)  # noqa: E712
        .where(TimeEntry.date >= from_date)
        .where(TimeEntry.date <= to_date)
    ).all()

    by_employee: dict[str, dict] = defaultdict(lambda: {
        "total_hours": Decimal("0"),
        "billable_hours": Decimal("0"),
        "total_cost": ZERO,
        "billable_cost": ZERO,
    })

    for te in entries:
        b = by_employee[te.employee_id]
        b["total_hours"] += to_decimal(te.hours)
        b["total_cost"] += to_decimal(te.total)
        if te.billable:
            b["billable_hours"] += to_decimal(te.hours)
            b["billable_cost"] += to_decimal(te.total)

    result = []
    for employee_id, b in by_employee.items():
        employee = session.get(Employee, employee_id)
        employee_name = employee.name if employee else employee_id
        result.append(EmployeeHoursRow(
            employee_id=employee_id,
            employee_name=employee_name,
            total_hours=float(b["total_hours"].quantize(Q, ROUND_HALF_UP)),
            billable_hours=float(b["billable_hours"].quantize(Q, ROUND_HALF_UP)),
            total_cost=float(b["total_cost"].quantize(Q, ROUND_HALF_UP)),
            billable_cost=float(b["billable_cost"].quantize(Q, ROUND_HALF_UP)),
        ))
    if format == "csv":
        filename = f"employee-hours-{from_date}-to-{to_date}.csv"
        return _to_csv(result, _EMPLOYEE_HOURS_FIELDS, filename)
    return result


# ── Top customers ─────────────────────────────────────────────────────────────

@router.get("/top-customers", response_model=list[TopCustomerRow])
def report_top_customers(
    ctx: CompanyContextDep,
    year: int,
    limit: int = 10,
    format: Optional[Literal["json", "csv"]] = "json",
) -> Union[list[TopCustomerRow], Response]:
    session = ctx.session
    company_id = ctx.company_id

    invoices = session.exec(
        select(Invoice)
        .where(Invoice.company_id == company_id)
        .where(Invoice.status != InvoiceStatus.draft)
        .where(Invoice.status != InvoiceStatus.cancelled)
        .where(Invoice.issue_date >= date(year, 1, 1))
        .where(Invoice.issue_date <= date(year, 12, 31))
    ).all()

    by_customer: dict[str, dict] = defaultdict(lambda: {
        "project_ids": set(),
        "invoiced_total": ZERO,
        "paid_total": ZERO,
    })

    for inv in invoices:
        b = by_customer[inv.customer_id]
        b["project_ids"].add(inv.project_id)
        b["invoiced_total"] += to_decimal(inv.total)
        if inv.status == InvoiceStatus.paid:
            b["paid_total"] += to_decimal(inv.total)

    rows = []
    for customer_id, b in by_customer.items():
        customer = session.get(Customer, customer_id)
        customer_name = customer.name if customer else customer_id
        invoiced_q = b["invoiced_total"].quantize(Q, ROUND_HALF_UP)
        paid_q = b["paid_total"].quantize(Q, ROUND_HALF_UP)
        rows.append(TopCustomerRow(
            customer_id=customer_id,
            customer_name=customer_name,
            project_count=len(b["project_ids"]),
            invoiced_total=float(invoiced_q),
            paid_total=float(paid_q),
        ))

    rows.sort(key=lambda r: r.invoiced_total, reverse=True)
    rows = rows[:limit]
    if format == "csv":
        return _to_csv(rows, _TOP_CUSTOMERS_FIELDS, f"top-customers-{year}.csv")
    return rows


# ── Expense breakdown ─────────────────────────────────────────────────────────

@router.get("/expense-breakdown", response_model=list[ExpenseCategoryRow])
def report_expense_breakdown(
    ctx: CompanyContextDep,
    year: int,
    format: Optional[Literal["json", "csv"]] = "json",
) -> Union[list[ExpenseCategoryRow], Response]:
    session = ctx.session
    company_id = ctx.company_id

    expenses = session.exec(
        select(Expense)
        .where(Expense.company_id == company_id)
        .where(Expense.active == True)  # noqa: E712
        .where(Expense.date >= date(year, 1, 1))
        .where(Expense.date <= date(year, 12, 31))
    ).all()

    by_category: dict[str, dict] = defaultdict(lambda: {
        "expense_count": 0,
        "total_excl_vat": ZERO,
        "total_vat": ZERO,
        "total_amount": ZERO,
    })

    for exp in expenses:
        b = by_category[exp.category.value]
        b["expense_count"] += 1
        b["total_excl_vat"] += to_decimal(exp.amount_excl_vat)
        b["total_vat"] += to_decimal(exp.vat_amount)
        b["total_amount"] += to_decimal(exp.amount_total)

    result = []
    for category, b in sorted(by_category.items()):
        result.append(ExpenseCategoryRow(
            category=category,
            expense_count=b["expense_count"],
            total_excl_vat=float(b["total_excl_vat"].quantize(Q, ROUND_HALF_UP)),
            total_vat=float(b["total_vat"].quantize(Q, ROUND_HALF_UP)),
            total_amount=float(b["total_amount"].quantize(Q, ROUND_HALF_UP)),
        ))
    if format == "csv":
        return _to_csv(result, _EXPENSE_BREAKDOWN_FIELDS, f"expense-breakdown-{year}.csv")
    return result
