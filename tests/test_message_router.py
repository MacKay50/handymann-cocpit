"""Unit tests for message_router service — no DB needed."""
from __future__ import annotations
from haandvaerker.services.message_router import classify_message
from haandvaerker.models.message_classification import (
    ClassificationSource,
    EntityType,
    MessageCategory,
)


def _classify(subject=None, body=None, **kw):
    return classify_message(subject=subject, body=body, **kw)


# ── category classification ──────────────────────────────────────────────────

def test_classifies_quote_request():
    result = _classify(
        subject="Forespørgsel om tilbud",
        body="Hej, vi ønsker tilbud på maling af vores villa.",
    )
    assert result.primary_category == MessageCategory.new_quote_request


def test_classifies_schedule_change():
    result = _classify(
        subject="Ændr aftale",
        body="Kan vi flytte vores aftale til en ny dato?",
    )
    assert result.primary_category == MessageCategory.schedule_change


def test_classifies_invoice_payment():
    result = _classify(
        subject="Faktura modtaget",
        body="Vi har modtaget faktura nr 2024-001.",
    )
    assert result.primary_category == MessageCategory.invoice_payment


def test_classifies_complaint():
    result = _classify(
        subject="Klage over arbejde",
        body="Vi er utilfredse med det udførte malerarbejde.",
    )
    assert result.primary_category == MessageCategory.complaint


def test_classifies_project_update():
    result = _classify(
        subject="Status på projekt",
        body="Hvad er status på projektet? Er arbejdet færdigt?",
    )
    assert result.primary_category == MessageCategory.project_update


def test_classifies_spam():
    result = _classify(
        subject="Winner!",
        body="Congratulations, click here to claim lottery prize!",
    )
    assert result.primary_category == MessageCategory.spam


def test_empty_message_classifies_other():
    result = _classify(subject=None, body=None)
    assert result.primary_category == MessageCategory.other


# ── boolean flags ─────────────────────────────────────────────────────────────

def test_quote_request_sets_is_quote_related():
    result = _classify(body="Ønsker tilbud på maling")
    assert result.is_quote_related is True
    assert result.requires_action is True


def test_schedule_change_sets_is_calendar_related():
    result = _classify(body="Vi skal flytte vores aftale til ny dato")
    assert result.is_calendar_related is True


def test_complaint_sets_priority_2():
    result = _classify(body="Vi klager over det udførte arbejde, vi er utilfredse")
    assert result.priority == 2


def test_quote_sets_priority_1():
    result = _classify(body="Ønsker tilbud på spartling og maling")
    assert result.priority == 1


# ── entity extraction ─────────────────────────────────────────────────────────

def test_extracts_danish_phone():
    result = _classify(body="Ring til mig på 23 45 67 89")
    phones = [e for e in result.entities if e.entity_type == EntityType.phone]
    assert len(phones) >= 1
    assert "23456789" in phones[0].value.replace(" ", "")


def test_extracts_email():
    result = _classify(body="Send tilbud til lars@example.com")
    emails = [e for e in result.entities if e.entity_type == EntityType.email]
    assert any("lars@example.com" == e.value for e in emails)


def test_extracts_address():
    result = _classify(body="Arbejdet skal udføres på Strandvej 42, 2900 Hellerup")
    addresses = [e for e in result.entities if e.entity_type == EntityType.address]
    assert len(addresses) >= 1


def test_extracts_project_reference():
    result = _classify(body="Vedr. sag SAG-2024-007")
    refs = [e for e in result.entities if e.entity_type == EntityType.project_reference]
    assert any("SAG-2024-007" in e.value for e in refs)


def test_extracts_amount():
    result = _classify(body="Beløbet er 15.000 kr. incl. moms")
    amounts = [e for e in result.entities if e.entity_type == EntityType.amount]
    assert len(amounts) >= 1


def test_sender_phone_included_in_entities():
    result = _classify(body="Ingen info", sender_phone="12345678")
    phones = [e for e in result.entities if e.entity_type == EntityType.phone]
    assert any("12345678" in e.value for e in phones)


def test_sender_email_included_in_entities():
    result = _classify(body="Ingen info", sender_email="test@test.dk")
    emails = [e for e in result.entities if e.entity_type == EntityType.email]
    assert any("test@test.dk" == e.value for e in emails)


def test_confidence_is_between_0_and_1():
    result = _classify(body="Ønsker tilbud på maling")
    assert 0.0 <= result.confidence <= 1.0


# ── LLM enrichment path ───────────────────────────────────────────────────────

def test_llm_enriches_low_confidence_result(monkeypatch):
    monkeypatch.setattr(
        "haandvaerker.services.message_router.local_ai.is_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "haandvaerker.services.message_router.local_ai.chat_completion",
        lambda **kw: '{"category": "new_quote_request", "is_urgent": false, "entities": [{"type": "person_name", "value": "Jan Hansen"}, {"type": "address", "value": "Roskildevej 42"}]}',
    )
    result = classify_message(subject=None, body="hej")
    assert result.primary_category == MessageCategory.new_quote_request
    assert result.classification_source == ClassificationSource.local_ai
    assert any(
        e.entity_type == EntityType.person_name and e.value == "Jan Hansen"
        for e in result.entities
    )
    assert result.is_quote_related is True
    assert result.priority == 1


def test_llm_malformed_json_falls_back(monkeypatch):
    monkeypatch.setattr(
        "haandvaerker.services.message_router.local_ai.is_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "haandvaerker.services.message_router.local_ai.chat_completion",
        lambda **kw: "Sure, here is some prose without any JSON braces at all.",
    )
    result = classify_message(subject=None, body="hej")
    assert result.classification_source == ClassificationSource.rule_based


def test_llm_invalid_category_falls_back(monkeypatch):
    monkeypatch.setattr(
        "haandvaerker.services.message_router.local_ai.is_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "haandvaerker.services.message_router.local_ai.chat_completion",
        lambda **kw: '{"category": "urgent_unknown_thing", "entities": []}',
    )
    result = classify_message(subject=None, body="hej")
    assert result.classification_source == ClassificationSource.rule_based
