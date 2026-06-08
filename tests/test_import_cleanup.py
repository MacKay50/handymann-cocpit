"""Tests for MIN-1 and MIN-2 import cleanup in api routers.

MIN-1: CompanyContext bare name must not be imported in any router except session.py.
MIN-2: SessionDep alias must not be defined in the 6 routers that never use it.
"""
import ast
import pathlib

API_DIR = pathlib.Path(__file__).parent.parent / "src" / "haandvaerker" / "api"

# MIN-1: routers that must NOT import CompanyContext (only CompanyContextDep)
MIN1_ROUTERS = [
    "action_items.py",
    "admin_deadlines.py",
    "appointments.py",
    "bank_transactions.py",
    "calendar_suggestions.py",
    "customers.py",
    "dashboard.py",
    "economic_customers.py",
    "economic_invoices.py",
    "employees.py",
    "enquiries.py",
    "expenses.py",
    "export_data.py",
    "historical_comparisons.py",
    "historical_offers.py",
    "inbox.py",
    "invoice_monitoring.py",
    "invoice_reminders.py",
    "invoices.py",
    "message_classifications.py",
    "payments.py",
    "project_communications.py",
    "projects.py",
    "quote_preparations.py",
    "quotes.py",
    "reconciliation.py",
    "reminders.py",
    "reports.py",
    "salaries.py",
    "time_entries.py",
    "vat_periods.py",
]

# MIN-2: routers that must NOT define SessionDep at module level
MIN2_ROUTERS = [
    "action_items.py",
    "customers.py",
    "enquiries.py",
    "inbox.py",
    "projects.py",
    "time_entries.py",
]


def _get_imported_names(filepath: pathlib.Path) -> set[str]:
    """Return all names imported from ..dependencies in the file."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "dependencies" in node.module:
                for alias in node.names:
                    names.add(alias.asname or alias.name)
    return names


def _defines_session_dep(filepath: pathlib.Path) -> bool:
    """Return True if the file defines SessionDep = ... at module level."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SessionDep":
                    return True
    return False


def test_min1_company_context_not_imported_in_non_session_routers():
    """CompanyContext bare name must not appear in imports outside session.py."""
    violations = []
    for fname in MIN1_ROUTERS:
        fpath = API_DIR / fname
        assert fpath.exists(), f"Expected router file not found: {fpath}"
        imported = _get_imported_names(fpath)
        if "CompanyContext" in imported:
            violations.append(fname)
    assert violations == [], (
        f"These routers still import CompanyContext (unused): {violations}"
    )


def test_min2_session_dep_not_defined_in_six_routers():
    """SessionDep alias must not be defined in the 6 routers that never use it."""
    violations = []
    for fname in MIN2_ROUTERS:
        fpath = API_DIR / fname
        assert fpath.exists(), f"Expected router file not found: {fpath}"
        if _defines_session_dep(fpath):
            violations.append(fname)
    assert violations == [], (
        f"These routers still define unused SessionDep: {violations}"
    )
