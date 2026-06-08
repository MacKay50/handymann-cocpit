import pathlib
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from .database import create_db_and_tables
from .api.admin_deadlines import router as admin_deadlines_router
from .api.appointments import router as appointments_router
from .api.dashboard import router as dashboard_router
from .api.companies import router as companies_router
from .api.customers import router as customers_router
from .api.employees import router as employees_router
from .api.enquiries import router as enquiries_router
from .api.projects import router as projects_router
from .api.quotes import router as quotes_router
from .api.time_entries import router as time_entries_router
from .api.expenses import router as expenses_router
from .api.invoices import router as invoices_router
from .api.payments import router as payments_router
from .api.inbox import router as inbox_router
from .api.reminders import router as reminders_router
from .api.reports import router as reports_router
from .api.salaries import router as salaries_router
from .api.vat_periods import router as vat_periods_router
from .api.quote_preparations import router as quote_preparations_router
from .api.historical_offers import router as historical_offers_router
from .api.historical_comparisons import router as historical_comparisons_router
from .api.message_classifications import router as message_classifications_router
from .api.project_communications import router as project_communications_router
from .api.action_items import router as action_items_router
from .api.calendar_suggestions import router as calendar_suggestions_router
from .api.export_data import router as export_data_router
from .api.bank_transactions import router as bank_transactions_router
from .api.economic_invoices import router as economic_invoices_router
from .api.economic_customers import router as economic_customers_router
from .api.reconciliation import router as reconciliation_router
from .api.invoice_monitoring import router as invoice_monitoring_router
from .api.invoice_reminders import router as invoice_reminders_router
from .api.session import router as session_router
from .api.intake import router as intake_router
from .api.jobs import router as jobs_router
from .api.wizard import router as wizard_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_db_and_tables()
    yield


app = FastAPI(
    title="Håndværker Business System",
    description="Intern styring af projekter, timer, udlæg og fakturering.",
    version="0.1.0",
    lifespan=lifespan,
)

_STATIC = pathlib.Path(__file__).parent / "static"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def landing() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def ui_dashboard() -> HTMLResponse:
    return HTMLResponse((_STATIC / "ui.html").read_text(encoding="utf-8"))


@app.get("/help", response_class=HTMLResponse, include_in_schema=False)
def help_page() -> HTMLResponse:
    return HTMLResponse((_STATIC / "help.html").read_text(encoding="utf-8"))


@app.get("/accept", response_class=HTMLResponse, include_in_schema=False)
def accept_page() -> HTMLResponse:
    return HTMLResponse((_STATIC / "accept.html").read_text(encoding="utf-8"))


@app.get("/print", response_class=HTMLResponse, include_in_schema=False)
def print_page() -> HTMLResponse:
    return HTMLResponse((_STATIC / "print.html").read_text(encoding="utf-8"))


@app.get("/export", response_class=HTMLResponse, include_in_schema=False)
def export_page() -> HTMLResponse:
    return HTMLResponse((_STATIC / "export.html").read_text(encoding="utf-8"))


@app.get("/reconciliation", response_class=HTMLResponse, include_in_schema=False)
def reconciliation_page() -> HTMLResponse:
    return HTMLResponse((_STATIC / "reconciliation.html").read_text(encoding="utf-8"))


@app.get("/betalingsradar", response_class=HTMLResponse, include_in_schema=False)
def betalingsradar_page() -> HTMLResponse:
    return HTMLResponse((_STATIC / "betalingsradar.html").read_text(encoding="utf-8"))


@app.get("/wizard", response_class=HTMLResponse, include_in_schema=False)
def wizard_page() -> HTMLResponse:
    return HTMLResponse((_STATIC / "wizard.html").read_text(encoding="utf-8"))


app.include_router(admin_deadlines_router)
app.include_router(appointments_router)
app.include_router(dashboard_router)
app.include_router(companies_router)
app.include_router(customers_router)
app.include_router(employees_router)
app.include_router(enquiries_router)
app.include_router(projects_router)
app.include_router(quotes_router)
app.include_router(time_entries_router)
app.include_router(expenses_router)
app.include_router(invoices_router)
app.include_router(payments_router)
app.include_router(inbox_router)
app.include_router(reminders_router)
app.include_router(reports_router)
app.include_router(salaries_router)
app.include_router(vat_periods_router)
app.include_router(quote_preparations_router)
app.include_router(historical_offers_router)
app.include_router(historical_comparisons_router)
app.include_router(message_classifications_router)
app.include_router(project_communications_router)
app.include_router(action_items_router)
app.include_router(calendar_suggestions_router)
app.include_router(export_data_router)
app.include_router(bank_transactions_router)
app.include_router(economic_invoices_router)
app.include_router(economic_customers_router)
app.include_router(reconciliation_router)
app.include_router(invoice_monitoring_router)
app.include_router(invoice_reminders_router)
app.include_router(session_router)
app.include_router(intake_router)
app.include_router(jobs_router)
app.include_router(wizard_router)

# Static file serving — mounted last so per-page HTML routes take priority.
# nav.js is served from here; HTML pages are served by individual @app.get routes above.
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
