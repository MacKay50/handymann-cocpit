"""Danish rule-based message classification and entity extraction.

Primary entry point: classify_message(inbox_message) -> ClassificationResult
Optional local AI enrichment when LOCAL_AI_ENDPOINT is set.
"""
from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from ..models.message_classification import (
    ClassificationSource,
    EntityType,
    MessageCategory,
)
from . import local_ai

logger = logging.getLogger(__name__)

# ── entity patterns ──────────────────────────────────────────────────────────

_RE_PHONE = re.compile(
    r"(?:\+45\s*)?(\d{2}\s?\d{2}\s?\d{2}\s?\d{2})\b"
)
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_RE_ADDRESS = re.compile(
    r"([A-ZÆØÅ][a-zæøå]+(?:\s[A-ZÆØÅ]?[a-zæøå]+)*\s+\d+[A-Za-z]?),?\s*(\d{4})\s+([A-ZÆØÅ][a-zæøå]+)",
    re.M,
)
_RE_DATE = re.compile(
    r"\b(\d{1,2})[./\-](\d{1,2})(?:[./\-](\d{2,4}))?\b"
    r"|\b(mandag|tirsdag|onsdag|torsdag|fredag|lørdag|søndag|"
    r"januar|februar|marts|april|maj|juni|juli|august|september|"
    r"oktober|november|december)\b",
    re.I,
)
_RE_TIME = re.compile(r"\b(\d{1,2})[.:](\d{2})\b")
_RE_PROJECT_REF = re.compile(
    r"\b(?:sag|projekt|kontrakt|ordre)[:\s#]*([A-Z0-9\-]+)\b", re.I
)
_RE_AMOUNT = re.compile(r"\b([\d.,]+)\s*kr\.?\b", re.I)

# ── category keyword maps ────────────────────────────────────────────────────

_CAT_KEYWORDS: dict[MessageCategory, list[str]] = {
    MessageCategory.new_quote_request: [
        "tilbud", "tilbuddet", "pris", "prisoverslag", "overslag",
        "hvad koster", "hvad vil det koste", "ønsker tilbud", "bede om tilbud",
        "maling", "male", "spartling", "tapet", "renovering", "istandsættelse",
    ],
    MessageCategory.project_update: [
        "projekt", "sagen", "arbejdet", "status", "færdig", "afsluttet",
        "påbegyndt", "opdatering", "fremgang",
    ],
    MessageCategory.schedule_change: [
        "aftale", "flytte", "rykke", "ændre dato", "ny dato", "annullere",
        "aflyse", "tidspunkt", "besøg", "møde",
    ],
    MessageCategory.invoice_payment: [
        "faktura", "betaling", "regning", "kvittering", "indbetalt",
        "betalte", "forfald",
    ],
    MessageCategory.complaint: [
        "klage", "utilfreds", "problem", "fejl", "mangelfuld", "dårlig",
        "ikke tilfreds", "reklamation",
    ],
    MessageCategory.general_inquiry: [
        "spørgsmål", "information", "forespørgsel", "henvendelse",
    ],
}

_SPAM_SIGNALS = ["unsubscribe", "click here", "winner", "congratulations",
                 "lottery", "casino"]

_LLM_CONFIDENCE_THRESHOLD = 0.6
_LLM_TIMEOUT_SECONDS = 8
_LLM_SYSTEM_PROMPT = (
    "Du er en klassifikationsassistent for en dansk håndværkervirksomhed. "
    "Returner KUN et JSON-objekt uden ekstra tekst. "
    "JSON-objektet skal have disse felter:\n"
    '- "category": en af disse værdier: "new_quote_request", "project_update", '
    '"schedule_change", "invoice_payment", "complaint", "general_inquiry", "spam", "other"\n'
    '- "is_urgent": true eller false\n'
    '- "entities": liste af objekter med "type" (en af: "person_name", "email", "phone", '
    '"address", "date_time", "project_reference", "amount", "company_name", "other") '
    'og "value" (streng)\n'
    "Eksempel: "
    '{"category": "new_quote_request", "is_urgent": false, '
    '"entities": [{"type": "person_name", "value": "Lars Jensen"}]}'
)


# ── result types ─────────────────────────────────────────────────────────────

@dataclass
class ExtractedEntity:
    entity_type: EntityType
    value: str
    normalized_value: Optional[str] = None
    confidence: float = 1.0


@dataclass
class ClassificationResult:
    primary_category: MessageCategory
    secondary_categories: list[MessageCategory] = field(default_factory=list)
    is_quote_related: bool = False
    is_project_related: bool = False
    is_calendar_related: bool = False
    requires_action: bool = False
    priority: int = 0
    confidence: float = 1.0
    classification_source: ClassificationSource = ClassificationSource.rule_based
    entities: list[ExtractedEntity] = field(default_factory=list)


# ── public entry point ───────────────────────────────────────────────────────

def classify_message(
    subject: Optional[str],
    body: Optional[str],
    sender_name: Optional[str] = None,
    sender_email: Optional[str] = None,
    sender_phone: Optional[str] = None,
    use_llm: bool = True,
) -> ClassificationResult:
    full_text = " ".join(filter(None, [subject, body]))
    lower = full_text.lower()

    result = _rule_classify(lower)
    result.entities = _extract_entities(
        full_text, sender_email, sender_phone
    )
    _derive_flags_and_priority(result)

    # NOTE: extract into llm_enrichment.py if Trin 2 reuses this pattern
    if use_llm and local_ai.is_enabled() and result.confidence < _LLM_CONFIDENCE_THRESHOLD:
        _enrich_with_llm(result, full_text)

    return result


# ── internal helpers ─────────────────────────────────────────────────────────

def _derive_flags_and_priority(result: ClassificationResult) -> None:
    """Mutates result in-place: derive boolean flags and priority from primary_category."""
    result.is_quote_related = result.primary_category == MessageCategory.new_quote_request
    result.is_project_related = result.primary_category in (
        MessageCategory.project_update, MessageCategory.complaint
    )
    result.is_calendar_related = result.primary_category == MessageCategory.schedule_change
    result.requires_action = result.primary_category in (
        MessageCategory.new_quote_request,
        MessageCategory.schedule_change,
        MessageCategory.complaint,
    )
    if result.primary_category == MessageCategory.complaint:
        result.priority = 2
    elif result.primary_category == MessageCategory.new_quote_request:
        result.priority = 1
    else:
        result.priority = 0


def _rule_classify(lower: str) -> ClassificationResult:
    if any(s in lower for s in _SPAM_SIGNALS):
        return ClassificationResult(primary_category=MessageCategory.spam, confidence=0.9)

    scores: dict[MessageCategory, int] = {}
    for cat, keywords in _CAT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score:
            scores[cat] = score

    if not scores:
        return ClassificationResult(
            primary_category=MessageCategory.other, confidence=0.5
        )

    primary = max(scores, key=lambda k: scores[k])
    secondaries = [c for c in scores if c != primary]

    total = sum(scores.values())
    confidence = round(scores[primary] / total, 2) if total else 0.5

    return ClassificationResult(
        primary_category=primary,
        secondary_categories=secondaries,
        confidence=confidence,
    )


def _extract_entities(
    text: str,
    sender_email: Optional[str],
    sender_phone: Optional[str],
) -> list[ExtractedEntity]:
    entities: list[ExtractedEntity] = []

    phones = {m.group(0).replace(" ", "") for m in _RE_PHONE.finditer(text)}
    if sender_phone:
        phones.add(sender_phone)
    for p in phones:
        entities.append(ExtractedEntity(EntityType.phone, p))

    emails = set(_RE_EMAIL.findall(text))
    if sender_email:
        emails.add(sender_email)
    for e in emails:
        entities.append(ExtractedEntity(EntityType.email, e))

    for m in _RE_ADDRESS.finditer(text):
        entities.append(ExtractedEntity(EntityType.address, m.group(0).strip()))

    for m in _RE_DATE.finditer(text):
        entities.append(ExtractedEntity(EntityType.date, m.group(0)))

    for m in _RE_TIME.finditer(text):
        entities.append(ExtractedEntity(EntityType.time, m.group(0)))

    for m in _RE_PROJECT_REF.finditer(text):
        entities.append(
            ExtractedEntity(EntityType.project_reference, m.group(1).strip())
        )

    for m in _RE_AMOUNT.finditer(text):
        entities.append(ExtractedEntity(EntityType.amount, m.group(0)))

    return entities


# ── LLM enrichment helpers ────────────────────────────────────────────────────

def _extract_json_safe(text: str) -> Optional[dict]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        logger.warning("LLM returned no JSON braces: %.200s", text)
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        logger.warning("LLM JSON parse failed: %.200s", text)
        return None


def _validate_llm_enrichment(
    raw: dict,
) -> Optional[tuple[MessageCategory, list[ExtractedEntity]]]:
    cat_str = raw.get("category")
    if not isinstance(cat_str, str) or not cat_str:
        logger.warning("LLM missing/invalid category field")
        return None
    try:
        category = MessageCategory(cat_str)
    except ValueError:
        logger.warning("LLM returned unknown category: %s", cat_str)
        return None

    entities: list[ExtractedEntity] = []
    for item in raw.get("entities", []):
        if not isinstance(item, dict):
            continue
        if "type" not in item or "value" not in item:
            continue
        try:
            entity_type = EntityType(item["type"])
        except ValueError:
            logger.warning("LLM unknown entity type: %s", item["type"])
            continue
        entities.append(
            ExtractedEntity(entity_type=entity_type, value=str(item["value"]))
        )
    return (category, entities)


def _enrich_with_llm(result: ClassificationResult, full_text: str) -> None:
    prompt = f"Besked:\n{full_text[:2000]}"
    response = local_ai.chat_completion(
        prompt=prompt,
        system=_LLM_SYSTEM_PROMPT,
        max_tokens=512,
        timeout=_LLM_TIMEOUT_SECONDS,
    )
    if response is None:
        logger.debug("LLM enrichment skipped (no response)")
        return
    parsed = _extract_json_safe(response)
    if parsed is None:
        logger.debug("LLM enrichment failed: JSON extraction")
        return
    validated = _validate_llm_enrichment(parsed)
    if validated is None:
        logger.debug("LLM enrichment failed: validation")
        return
    category, entities = validated
    result.primary_category = category
    # Merge: keep rule-extracted entities (phone/email/address/amount/date),
    # append LLM-only types (person_name, company_name) not already present.
    rule_types = {e.entity_type for e in result.entities}
    result.entities = result.entities + [e for e in entities if e.entity_type not in rule_types]
    result.classification_source = ClassificationSource.local_ai
    _derive_flags_and_priority(result)
