"""Assert each Phase 2 field is present on its Read schema with the correct default."""
from haandvaerker.models.time_entry import TimeEntryRead
from haandvaerker.models.invoice_reminder import InvoiceReminderRead
from haandvaerker.models.project import ProjectRead
from haandvaerker.models.quote import QuoteRead
from haandvaerker.models.enquiry import EnquiryRead
from haandvaerker.models.economic_invoice import EconomicInvoiceRead


def test_time_entry_has_action_item_id():
    fields = TimeEntryRead.model_fields
    assert "action_item_id" in fields
    assert fields["action_item_id"].default is None


def test_invoice_reminder_has_triggered_by():
    fields = InvoiceReminderRead.model_fields
    assert "triggered_by" in fields
    assert fields["triggered_by"].default == "manual"


def test_project_has_close_fields():
    fields = ProjectRead.model_fields
    assert "close_reason" in fields
    assert "close_override" in fields
    assert fields["close_reason"].default is None
    assert fields["close_override"].default is False


def test_quote_has_quote_type():
    fields = QuoteRead.model_fields
    assert "quote_type" in fields
    assert fields["quote_type"].default == "line"


def test_enquiry_has_qualification_fields():
    fields = EnquiryRead.model_fields
    for f in ("address", "work_type", "timeframe"):
        assert f in fields, f"Missing field: {f}"
        assert fields[f].default is None


def test_economic_invoice_has_invoice_id():
    fields = EconomicInvoiceRead.model_fields
    assert "invoice_id" in fields
    assert fields["invoice_id"].default is None
