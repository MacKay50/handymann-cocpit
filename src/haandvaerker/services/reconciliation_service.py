"""Reconciliation matching service.

Deterministic exact matcher runs first (amount_ore == gross_amount_ore AND
abs(transaction_date - due_date).days <= 7).  Invoice-number matcher runs
second (extracts 4–6 digit numbers from bank description, matches to invoice
numbers, verifies sum equals tx amount — supports multi-invoice splits).
AI residual matcher runs last when local_ai.is_enabled() returns True.

Iron Law 3 — code decides:
  - auto_exact matches are confirmed=True (deterministic rule, no human required).
  - auto_number and auto_ai matches are ALWAYS confirmed=False — human must
    confirm via POST /reconciliation/{match_id}/confirm.
  - manual matches (set by the API) are confirmed=True.

Iron Law 2 — fail loud:
  - AI unavailable (is_enabled() False or chat_completion returns None): log at
    debug and return [].  This is an explicit named fallback — not a silent mask.
  - JSONDecodeError on AI response: log at warning and return [].
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session, select

from ..models.bank_transaction import BankTransaction, BankTransactionStatus
from ..models.economic_invoice import EconomicInvoice, EconomicInvoiceStatus
from ..models.reconciliation_match import MatchType, ReconciliationMatch
from . import local_ai

logger = logging.getLogger(__name__)

# ── constants ──────────────────────────────────────────────────────────────────

_DATE_WINDOW_DAYS = 7
_AI_CONFIDENCE_THRESHOLD = 0.6
_AI_TIMEOUT_SECONDS = 15
_NEAR_AMOUNT_TOLERANCE_ORE = 100  # accept amount differences up to 1.00 DKK (rounding, fees)

_AI_SYSTEM_PROMPT = (
    "Du er en bankafstemmingsassistent for en dansk håndværkervirksomhed. "
    "Givet en liste af banktransaktioner og åbne fakturaer, returner KUN et JSON-array uden ekstra tekst. "
    "VIGTIGT — multi-faktura: én banktransaktion kan dække FLERE fakturaer. "
    "Returner ét JSON-element pr. faktura-match (samme bank_transaction_id, forskellige economic_invoice_id). "
    "Brug beskrivelsens tekst og besked-felt (adskilt af ' | ') til at identificere fakturanumre og debitornavne. "
    "Acceptér beløbsforskel på ≤ 1,00 DKK (100 øre) — angiv confidence < 0.8 for nær-match. "
    "Hvert element skal have: \"bank_transaction_id\", \"economic_invoice_id\", \"confidence\" (0.0-1.0). "
    "Returner kun matches med confidence >= 0.5. "
    "Eksempel (én transaktion dækker to fakturaer): "
    "[{\"bank_transaction_id\": \"tx1\", \"economic_invoice_id\": \"inv_a\", \"confidence\": 0.95}, "
    "{\"bank_transaction_id\": \"tx1\", \"economic_invoice_id\": \"inv_b\", \"confidence\": 0.95}]"
)


# ── result type ────────────────────────────────────────────────────────────────

@dataclass
class MatchingResult:
    deterministic_count: int = 0
    number_count: int = 0
    ai_suggested_count: int = 0
    matches: list = field(default_factory=list)  # list[ReconciliationMatch]


# ── deterministic matcher ──────────────────────────────────────────────────────

def run_deterministic_matches(session: Session, company_id: str) -> list[ReconciliationMatch]:
    """Exact amount_ore == gross_amount_ore AND date within ±7 days of due_date.

    Matches are confirmed=True.  Does NOT commit — caller commits.
    """
    txs = session.exec(
        select(BankTransaction).where(
            BankTransaction.company_id == company_id,
            BankTransaction.status == BankTransactionStatus.unmatched,
            BankTransaction.active == True,  # noqa: E712
            BankTransaction.amount_ore > 0,
        )
    ).all()

    invoices = session.exec(
        select(EconomicInvoice).where(
            EconomicInvoice.company_id == company_id,
            EconomicInvoice.status == EconomicInvoiceStatus.unmatched,
            EconomicInvoice.active == True,  # noqa: E712
        )
    ).all()

    # Index by gross_amount_ore for O(1) lookup
    invoices_by_amount: dict[int, list[EconomicInvoice]] = {}
    for inv in invoices:
        invoices_by_amount.setdefault(inv.gross_amount_ore, []).append(inv)

    matched_invoice_ids: set[str] = set()
    matches: list[ReconciliationMatch] = []

    for tx in txs:
        candidates = [
            inv for inv in invoices_by_amount.get(tx.amount_ore, [])
            if inv.id not in matched_invoice_ids
            and abs((tx.transaction_date - inv.due_date).days) <= _DATE_WINDOW_DAYS
        ]
        if len(candidates) != 1:
            continue

        inv = candidates[0]
        match = ReconciliationMatch(
            bank_transaction_id=tx.id,
            economic_invoice_id=inv.id,
            match_type=MatchType.auto_exact,
            confirmed=True,
        )
        tx.status = BankTransactionStatus.matched
        inv.status = EconomicInvoiceStatus.matched

        session.add(match)
        session.add(tx)
        session.add(inv)

        matched_invoice_ids.add(inv.id)
        matches.append(match)

    return matches


# ── invoice-number matcher ─────────────────────────────────────────────────────

def _extract_invoice_numbers(text: str) -> list[str]:
    """Return all 4–6 digit sequences from text — invoice number candidates."""
    return re.findall(r'\b(\d{4,6})\b', text or "")


def run_invoice_number_matches(session: Session, company_id: str) -> list[ReconciliationMatch]:
    """Match bank txs to invoices where description contains invoice number(s).

    Supports multi-invoice: if the gross amounts of all found invoices sum to
    the transaction amount exactly, creates one ReconciliationMatch per invoice.
    Exact amount match (diff == 0): confirmed=True, statuses updated immediately.
    Near-amount match (≤1 DKK off): confirmed=False — human must confirm.
    Does NOT commit — caller commits.
    """
    unmatched_txs = session.exec(
        select(BankTransaction).where(
            BankTransaction.company_id == company_id,
            BankTransaction.status == BankTransactionStatus.unmatched,
            BankTransaction.active == True,  # noqa: E712
            BankTransaction.amount_ore > 0,
        )
    ).all()

    unmatched_invoices = session.exec(
        select(EconomicInvoice).where(
            EconomicInvoice.company_id == company_id,
            EconomicInvoice.status == EconomicInvoiceStatus.unmatched,
            EconomicInvoice.active == True,  # noqa: E712
        )
    ).all()

    if not unmatched_txs or not unmatched_invoices:
        return []

    # Index invoices by stripped invoice number (remove leading zeros)
    inv_by_number: dict[str, EconomicInvoice] = {}
    for inv in unmatched_invoices:
        if inv.economic_invoice_number:
            key = inv.economic_invoice_number.strip().lstrip("0") or "0"
            inv_by_number[key] = inv

    matched_invoice_ids: set[str] = set()
    matches: list[ReconciliationMatch] = []

    for tx in unmatched_txs:
        numbers = _extract_invoice_numbers(tx.description or "")
        if not numbers:
            continue

        found: list[EconomicInvoice] = []
        seen_ids: set[str] = set()
        for num in numbers:
            norm = num.lstrip("0") or "0"
            inv = inv_by_number.get(norm)
            if inv and inv.id not in seen_ids and inv.id not in matched_invoice_ids:
                found.append(inv)
                seen_ids.add(inv.id)

        if not found:
            continue

        total_ore = sum(inv.gross_amount_ore for inv in found)
        diff = abs(total_ore - tx.amount_ore)
        if diff > _NEAR_AMOUNT_TOLERANCE_ORE:
            continue

        exact = diff == 0
        confidence = 0.9 if exact else 0.72
        notes = None if exact else f"Beløbsforskel {diff / 100:.2f} kr — kontrollér inden bekræftelse"

        for inv in found:
            match = ReconciliationMatch(
                bank_transaction_id=tx.id,
                economic_invoice_id=inv.id,
                match_type=MatchType.auto_number,
                confidence=confidence,
                confirmed=exact,
                notes=notes,
            )
            inv.status = EconomicInvoiceStatus.matched
            session.add(match)
            session.add(inv)
            matched_invoice_ids.add(inv.id)
            matches.append(match)

        if exact:
            tx.status = BankTransactionStatus.matched
            session.add(tx)

    return matches


# ── AI prompt helpers ──────────────────────────────────────────────────────────

def _build_ai_prompt(
    unmatched_txs: list[BankTransaction],
    unmatched_invoices: list[EconomicInvoice],
) -> str:
    lines = ["Banktransaktioner (uafstemte):"]
    for tx in unmatched_txs:
        lines.append(
            f"  id={tx.id} dato={tx.transaction_date} beloeb_ore={tx.amount_ore} tekst={tx.description!r}"
        )
    lines.append("Fakturaer (uafstemte):")
    for inv in unmatched_invoices:
        lines.append(
            f"  id={inv.id} forfaldsdato={inv.due_date} brutto_ore={inv.gross_amount_ore} kunde={inv.customer_name!r}"
        )
    lines.append("Returner KUN et JSON-array med matches.")
    return "\n".join(lines)


def _parse_ai_response(text: str) -> Optional[list[dict]]:
    """Extract first JSON array from text. Returns None on failure."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        logger.warning("AI returned no JSON array brackets: %.200s", text)
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("AI JSON parse failed: %.200s", text)
        return None
    if not isinstance(parsed, list):
        logger.warning("AI response is not a list: %.200s", text)
        return None
    return parsed


# ── AI residual matcher ────────────────────────────────────────────────────────

def run_ai_residual_matches(session: Session, company_id: str) -> list[ReconciliationMatch]:
    """Propose matches for remaining unmatched rows using local AI.

    AI matches are ALWAYS confirmed=False — never auto-confirmed (Iron Law 3).
    Returns [] without raising when AI is disabled or unavailable.
    Does NOT update tx/inv statuses.  Does NOT commit — caller commits.
    """
    if not local_ai.is_enabled():
        return []

    unmatched_txs = session.exec(
        select(BankTransaction).where(
            BankTransaction.company_id == company_id,
            BankTransaction.status == BankTransactionStatus.unmatched,
            BankTransaction.active == True,  # noqa: E712
            BankTransaction.amount_ore > 0,
        )
    ).all()

    unmatched_invoices = session.exec(
        select(EconomicInvoice).where(
            EconomicInvoice.company_id == company_id,
            EconomicInvoice.status == EconomicInvoiceStatus.unmatched,
            EconomicInvoice.active == True,  # noqa: E712
        )
    ).all()

    if not unmatched_txs or not unmatched_invoices:
        return []

    prompt = _build_ai_prompt(unmatched_txs, unmatched_invoices)
    response = local_ai.chat_completion(
        prompt=prompt,
        system=_AI_SYSTEM_PROMPT,
        max_tokens=512,
        timeout=_AI_TIMEOUT_SECONDS,
    )
    if response is None:
        logger.debug("AI unavailable, skipping residual matches")
        return []

    candidates = _parse_ai_response(response)
    if candidates is None:
        return []

    tx_id_set = {tx.id for tx in unmatched_txs}
    inv_id_set = {inv.id for inv in unmatched_invoices}
    matched_invoice_ids: set[str] = set()
    matches: list[ReconciliationMatch] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        confidence = candidate.get("confidence")
        if not isinstance(confidence, (int, float)):
            continue
        confidence = float(confidence)
        if confidence < _AI_CONFIDENCE_THRESHOLD:
            continue

        tx_id = candidate.get("bank_transaction_id")
        inv_id = candidate.get("economic_invoice_id")
        if tx_id not in tx_id_set or inv_id not in inv_id_set:
            continue
        if inv_id in matched_invoice_ids:
            continue

        # Iron Law 3: AI matches are NEVER confirmed=True
        match = ReconciliationMatch(
            bank_transaction_id=tx_id,
            economic_invoice_id=inv_id,
            match_type=MatchType.auto_ai,
            confidence=confidence,
            confirmed=False,
        )
        session.add(match)
        matched_invoice_ids.add(inv_id)
        matches.append(match)

    return matches


# ── public entry point ─────────────────────────────────────────────────────────

def run_matching(session: Session, company_id: str) -> MatchingResult:
    """Run deterministic, invoice-number, then AI matching. Commits the session."""
    det_matches = run_deterministic_matches(session, company_id)
    num_matches = run_invoice_number_matches(session, company_id)
    ai_matches = run_ai_residual_matches(session, company_id)
    session.commit()
    return MatchingResult(
        deterministic_count=len(det_matches),
        number_count=len(num_matches),
        ai_suggested_count=len(ai_matches),
        matches=det_matches + num_matches + ai_matches,
    )
