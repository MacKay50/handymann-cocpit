"""Rule-based structured extraction from raw offer text.

Produces a dict matching HistoricalOffer fields. Values left as None when
the pattern doesn't fire — never fabricates data (Iron Law 2).
"""
from __future__ import annotations
import re
from typing import Optional


# ── compiled patterns ────────────────────────────────────────────────────────

_RE_PRICE_EX = re.compile(
    r"(?:pris\s+(?:ex\.?\s*moms|uden\s+moms)[:\s]*)([\d.,]+)", re.I
)
_RE_PRICE_INC = re.compile(
    r"(?:pris\s+(?:inkl\.?\s*moms|med\s+moms)[:\s]*)([\d.,]+)", re.I
)
_RE_TOTAL = re.compile(
    r"(?:total|i\s+alt|samlet)[:\s]*([\d.,]+)\s*kr", re.I
)
_RE_AREA = re.compile(r"([\d.,]+)\s*m[²2]", re.I)
_RE_YEAR = re.compile(r"\b(20\d{2})\b")
_RE_OFFER_NUM = re.compile(r"(?:tilbud(?:snr\.?|nummer)?[:\s#]*)([\w-]+)", re.I)
_RE_HOURS = re.compile(r"([\d.,]+)\s*timer?", re.I)
_RE_ADDRESS = re.compile(
    r"([A-ZÆØÅ][a-zæøå]+(?:\s[A-ZÆØÅ]?[a-zæøå]+)*\s+\d+[A-Za-z]?),?\s*(\d{4})\s+([A-ZÆØÅ][a-zæøå]+)",
    re.M,
)

_JOB_KEYWORDS: dict[str, list[str]] = {
    "maling": ["male", "maling", "maler", "loftsmaling", "vægmaling"],
    "spartling": ["spartle", "spartling"],
    "tapet": ["tapet", "tapetsere", "tapetlægning"],
    "rengøring": ["rengøring", "clean"],
    "facade": ["facade", "udvendig"],
    "gulv": ["gulv", "parket", "laminat"],
    "fliser": ["fliser", "flisning", "klinker"],
    "loft": ["loft", "nedsænket loft"],
}

_BUILDING_KEYWORDS: dict[str, list[str]] = {
    "villa": ["villa", "hus", "enfamiliehus"],
    "rækkehus": ["rækkehus"],
    "lejlighed": ["lejlighed", "ejerlejlighed", "andelslejlighed"],
    "erhverv": ["erhverv", "kontor", "butik"],
}

_CUSTOMER_KEYWORDS: dict[str, list[str]] = {
    "privat": ["privat", "boligejer"],
    "erhverv": ["erhverv", "virksomhed", "cvr"],
    "boligforening": ["ejerforening", "andelsforening", "boligforening"],
}


def _parse_float(raw: str) -> Optional[float]:
    cleaned = raw.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_offer_fields(text: str) -> dict:
    """Return partial HistoricalOffer field dict from *text*."""
    result: dict = {}

    m = _RE_OFFER_NUM.search(text)
    if m:
        result["offer_number"] = m.group(1).strip()

    years = _RE_YEAR.findall(text)
    if years:
        result["year"] = int(years[0])

    m = _RE_PRICE_EX.search(text)
    if m:
        result["price_ex_vat"] = _parse_float(m.group(1))

    m = _RE_PRICE_INC.search(text)
    if m:
        result["price_inc_vat"] = _parse_float(m.group(1))

    if "price_inc_vat" not in result:
        m = _RE_TOTAL.search(text)
        if m:
            result["price_inc_vat"] = _parse_float(m.group(1))

    areas = [_parse_float(a) for a in _RE_AREA.findall(text) if _parse_float(a)]
    if areas:
        result["area_m2"] = max(areas)

    hours = _RE_HOURS.findall(text)
    if hours:
        parsed = [_parse_float(h) for h in hours if _parse_float(h)]
        if parsed:
            result["estimated_hours"] = max(parsed)

    lower = text.lower()
    for job_type, keywords in _JOB_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            result["job_type"] = job_type
            break

    for building_type, keywords in _BUILDING_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            result["building_type"] = building_type
            break

    for customer_type, keywords in _CUSTOMER_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            result["customer_type"] = customer_type
            break

    m_addr = _RE_ADDRESS.search(text)
    if m_addr:
        result["title"] = m_addr.group(0).strip()

    return result
