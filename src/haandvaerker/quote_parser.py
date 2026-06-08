from __future__ import annotations
import re
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models.inbox_message import InboxMessage

_KEYWORD_GROUPS: dict[str, list[str]] = {
    "kælder": ["kælder"],
    "facade": ["facade", "facader", "gavl"],
    "træværk": ["træværk", "vinduer", "vinduesrammer", "gesims"],
    "lejlighed": ["lejlighed", "lejl.", "ejerlejlighed"],
    "hus": ["parcelhus", "villa", "rækkehus", " hus "],
    "kontor": ["kontor", "kontorlokale"],
    "klinik": ["klinik"],
    "skimmel": ["skimmel", "svamp", "fugtskade"],
    "spartling": ["spartling", "spartle", "spartlet"],
    "filt": ["filtmaling", "filt"],
    "maling": ["maling", " male ", "maler", "lakering", " lak "],
}

_NOTE = "kræver manuel vurdering"
_NOTE_M2 = "kræver manuel vurdering — m2 ukendt"


def _line(
    desc: str, unit: str = "stk", qty: float = 1, price: float = 0.0, note: str = _NOTE
) -> dict:
    return {"description": desc, "unit": unit, "quantity": qty, "unit_price": price, "notes": note}


def _extract_phone(text: str) -> Optional[str]:
    text = text or ""
    m = re.search(r"\+45[\s\-]?(\d[\s\-]?){8}", text)
    if m:
        return re.sub(r"[\s\-]", "", m.group(0))
    m = re.search(r"\b(\d{2}[\s]?\d{2}[\s]?\d{2}[\s]?\d{2})\b", text)
    if m:
        digits = re.sub(r"\s", "", m.group(1))
        if len(digits) == 8:
            return digits
    return None


def _extract_address(text: str) -> Optional[str]:
    text = text or ""
    m = re.search(r"adresse[n]?[:]\s*([^\n]+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"[A-ZÆØÅ][a-zæøåA-ZÆØÅ\s]+ \d{1,4}[A-Za-z]?,?\s*\d{4}\s+[A-ZÆØÅ][a-zæøå]+",
        text,
    )
    if m:
        return m.group(0).strip()
    return None


def _detect_keywords(text: str) -> list[str]:
    tl = " " + (text or "").lower() + " "
    return [kt for kt, synonyms in _KEYWORD_GROUPS.items() if any(kw in tl for kw in synonyms)]


def _generate_lines(keywords: list[str]) -> list[dict]:
    kw = set(keywords)
    lines: list[dict] = [
        _line("Besigtigelse og opmåling"),
        _line("Afdækning og klargøring"),
    ]
    if kw & {"spartling", "skimmel"}:
        lines += [
            _line("Spartling / reparation"),
            _line("Slibning"),
        ]
    lines.append(_line("Grunding"))
    if kw & {"maling", "lejlighed", "hus", "kontor", "klinik", "kælder"}:
        lines.append(_line("Maling af vægge og lofter", unit="m2", note=_NOTE_M2))
    if kw & {"træværk", "facade"}:
        lines.append(_line("Maling af træværk / facade"))
    if "filt" in kw:
        lines.append(_line("Filtmaling", unit="m2", note=_NOTE_M2))
    return lines


def _generate_missing_info(
    address: Optional[str], text: str, keywords: list[str]
) -> list[str]:
    tl = (text or "").lower()
    missing: list[str] = []
    if not address:
        missing.append("Adresse / lokation")
    area_tasks = {"maling", "lejlighed", "hus", "kontor", "klinik", "kælder", "filt", "spartling"}
    if set(keywords) & area_tasks and not re.search(r"\d+\s*m2", tl):
        missing.append("Areal i m2")
    if not re.search(r"foto|billede|billeder|fotos", tl):
        missing.append("Fotos / billeder af opgaven")
    if not re.search(r"deadline|senest|inden|startdato|uge|måned", tl):
        missing.append("Ønsket startdato / deadline")
    if not re.search(r"adgang|nøgle|nøgler|portcode|kode", tl):
        missing.append("Adgangsforhold")
    return missing


def parse_inbox_message(msg: "InboxMessage") -> dict:
    full_text = " ".join(filter(None, [msg.subject, msg.body]))
    phone = msg.sender_phone or _extract_phone(full_text)
    address = _extract_address(full_text)
    keywords = _detect_keywords(full_text)
    return {
        "customer_name": msg.sender_name,
        "customer_email": msg.sender_email,
        "customer_phone": phone,
        "address": address,
        "task_type": keywords[0] if keywords else None,
        "short_summary": msg.subject or (full_text[:200] if full_text else None),
        "detailed_description": msg.body,
        "suggested_lines": _generate_lines(keywords),
        "missing_info": _generate_missing_info(address, full_text, keywords),
        "rooms": [],
    }
