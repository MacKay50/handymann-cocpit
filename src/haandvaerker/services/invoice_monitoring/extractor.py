"""InvoiceFieldExtractor — stub implementation using regex heuristics.

Real implementation would call a local LLM. This stub parses common Danish
invoice text patterns so tests and dev ingestion work without AI infrastructure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class EvidenceItem:
    field_name: str
    extracted_value: Optional[str]
    source_text: str
    confidence: float


@dataclass
class ExtractionResult:
    creditor_name: Optional[str]
    invoice_number: Optional[str]
    customer_number: Optional[str]
    amount_ore: Optional[int]
    currency: str
    invoice_date: Optional[date]
    due_date: Optional[date]
    payment_reference: Optional[str]
    is_reminder: bool
    reminder_level: Optional[int]
    confidence: float
    evidence: list[EvidenceItem] = field(default_factory=list)


# ── patterns ──────────────────────────────────────────────────────────────────

_AMOUNT_RE = re.compile(r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)\s*(?:kr\.?|dkk)', re.IGNORECASE)
_DATE_RE = re.compile(r'\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b')
_INVOICE_NR_RE = re.compile(
    r'(?:faktura\s*(?:nr\.?|nummer|#)\s*|invoice\s*(?:nr\.?|no\.?|#)\s*)([A-Z0-9\-]{3,20})',
    re.IGNORECASE,
)
_PAYMENT_REF_RE = re.compile(
    r'(?:betalingsreference|payment\s*ref(?:erence)?|ref\.?|ocr)[:\s]+([A-Z0-9\-\s]{4,30})',
    re.IGNORECASE,
)
_REMINDER_LEVEL_RE = re.compile(r'(\d+)\.\s*rykker|rykker\s*(\d+)', re.IGNORECASE)
_FROM_RE = re.compile(r'^fra[:\s]+(.+)$', re.IGNORECASE | re.MULTILINE)


def _parse_danish_amount(s: str) -> int:
    """Convert Danish amount string (e.g. '1.234,56') to øre."""
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return round(float(s) * 100)
    except ValueError:
        return 0


def _parse_date(day: str, month: str, year: str) -> Optional[date]:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def extract(text: str, subject: str = "", sender: str = "") -> ExtractionResult:
    """Extract invoice fields from document text using regex heuristics."""
    combined = f"{subject}\n{text}"
    evidence: list[EvidenceItem] = []
    confidence_factors: list[float] = []

    # Amount
    amount_ore: Optional[int] = None
    m = _AMOUNT_RE.search(combined)
    if m:
        amount_ore = _parse_danish_amount(m.group(1))
        evidence.append(EvidenceItem("amount", str(amount_ore), m.group(0), 0.8))
        confidence_factors.append(0.8)

    # Invoice number
    invoice_number: Optional[str] = None
    m = _INVOICE_NR_RE.search(combined)
    if m:
        invoice_number = m.group(1).strip()
        evidence.append(EvidenceItem("invoice_number", invoice_number, m.group(0), 0.9))
        confidence_factors.append(0.9)

    # Dates — first match = invoice date, second = due date
    dates = [_parse_date(d, mo, y) for d, mo, y in _DATE_RE.findall(combined)]
    dates = [d for d in dates if d is not None]
    invoice_date = dates[0] if dates else None
    due_date = dates[1] if len(dates) > 1 else dates[0] if dates else None
    if due_date:
        evidence.append(EvidenceItem("due_date", str(due_date), "", 0.7))
        confidence_factors.append(0.7)

    # Payment reference
    payment_reference: Optional[str] = None
    m = _PAYMENT_REF_RE.search(combined)
    if m:
        payment_reference = m.group(1).strip()
        evidence.append(EvidenceItem("payment_reference", payment_reference, m.group(0), 0.75))

    # Creditor name: try sender field first, then "Fra: ..." pattern
    creditor_name: Optional[str] = None
    if sender:
        # "Hansen Byggeri <invoice@hansen.dk>" → "Hansen Byggeri"
        name_part = re.sub(r'\s*<[^>]+>', '', sender).strip()
        if name_part:
            creditor_name = name_part
            evidence.append(EvidenceItem("creditor_name", creditor_name, sender, 0.7))
            confidence_factors.append(0.7)
    if not creditor_name:
        m = _FROM_RE.search(combined)
        if m:
            creditor_name = m.group(1).strip()
            evidence.append(EvidenceItem("creditor_name", creditor_name, m.group(0), 0.6))
            confidence_factors.append(0.6)

    # Reminder detection
    is_reminder = bool(re.search(r'rykker|påmindelse|reminder|overdue', combined, re.IGNORECASE))
    reminder_level: Optional[int] = None
    m = _REMINDER_LEVEL_RE.search(combined)
    if m:
        lvl = m.group(1) or m.group(2)
        reminder_level = int(lvl) if lvl else 1
    elif is_reminder:
        reminder_level = 1

    overall_confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.3

    return ExtractionResult(
        creditor_name=creditor_name,
        invoice_number=invoice_number,
        customer_number=None,
        amount_ore=amount_ore,
        currency="DKK",
        invoice_date=invoice_date,
        due_date=due_date,
        payment_reference=payment_reference,
        is_reminder=is_reminder,
        reminder_level=reminder_level,
        confidence=min(overall_confidence, 1.0),
        evidence=evidence,
    )
