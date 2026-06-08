"""Reconciliation API — bank-centric matching endpoints.

Route registration order (CODE-09): fixed-path routes BEFORE /{match_id}
  1. POST /reconciliation/match
  2. POST /reconciliation/manual-match
  3. GET  /reconciliation/
  4. GET  /reconciliation/bank-view
  5. POST /reconciliation/confirm-all
  6. POST /reconciliation/{match_id}/confirm
  7. POST /reconciliation/{match_id}/reject
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..dependencies import CompanyContextDep
from ..models.bank_transaction import BankTransaction, BankTransactionRead, BankTransactionStatus
from ..models.economic_invoice import (
    EconomicInvoice,
    EconomicInvoiceStatus,
)
from ..models.reconciliation_match import MatchType, ReconciliationMatch, ReconciliationMatchRead
from ..services.reconciliation_service import run_matching
from .economic_invoices import EconomicInvoiceRead, _to_read as _invoice_read

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


# ── response models ────────────────────────────────────────────────────────────

class MatchingResultRead(BaseModel):
    deterministic_count: int
    number_count: int = 0
    ai_suggested_count: int
    matches: list[ReconciliationMatchRead]


class ReconciliationItemRead(BaseModel):
    economic_invoice: EconomicInvoiceRead
    match: Optional[ReconciliationMatchRead]
    bank_transaction: Optional[BankTransactionRead]
    reconciliation_status: str  # 'matched', 'proposed', 'overdue', 'unmatched'


class ReconciliationViewRead(BaseModel):
    items: list[ReconciliationItemRead]
    orphan_transactions: list[BankTransactionRead]


class ManualMatchRequest(BaseModel):
    bank_transaction_id: str
    economic_invoice_id: str
    notes: Optional[str] = None


class ConfirmAllResult(BaseModel):
    confirmed_matches: int
    confirmed_transactions: int
    skipped_transactions: int


class InvoiceMatchPairRead(BaseModel):
    invoice: EconomicInvoiceRead
    match: ReconciliationMatchRead


class BankTransactionWithMatchesRead(BaseModel):
    transaction: BankTransactionRead
    matches: list[InvoiceMatchPairRead]
    bank_status: str  # 'matched', 'proposed', 'unmatched'


class BankViewRead(BaseModel):
    rows: list[BankTransactionWithMatchesRead]
    stats: dict


# ── 1. POST /reconciliation/match ─────────────────────────────────────────────

@router.post("/match", response_model=MatchingResultRead, status_code=201)
def run_match(ctx: CompanyContextDep) -> MatchingResultRead:
    """Run deterministic, invoice-number, then AI matching for all unmatched rows."""
    session = ctx.session
    result = run_matching(session, ctx.company_id)
    return MatchingResultRead(
        deterministic_count=result.deterministic_count,
        number_count=result.number_count,
        ai_suggested_count=result.ai_suggested_count,
        matches=[
            ReconciliationMatchRead.model_validate(m, from_attributes=True)
            for m in result.matches
        ],
    )


# ── 2. POST /reconciliation/manual-match ─────────────────────────────────────

@router.post("/manual-match", response_model=ReconciliationMatchRead, status_code=201)
def manual_match(body: ManualMatchRequest, ctx: CompanyContextDep) -> ReconciliationMatchRead:
    """Manually link a bank transaction to an invoice (same company only)."""
    session = ctx.session
    tx = session.get(BankTransaction, body.bank_transaction_id)
    inv = session.get(EconomicInvoice, body.economic_invoice_id)

    if not tx or not tx.active:
        raise HTTPException(
            status_code=422,
            detail=f"BankTransaction '{body.bank_transaction_id}' ikke fundet",
        )
    if not inv or not inv.active:
        raise HTTPException(
            status_code=422,
            detail=f"EconomicInvoice '{body.economic_invoice_id}' ikke fundet",
        )
    if tx.company_id != ctx.company_id or inv.company_id != ctx.company_id:
        raise HTTPException(
            status_code=422,
            detail="BankTransaction og EconomicInvoice tilhører ikke din virksomhed",
        )

    existing_matches = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.bank_transaction_id == tx.id,
            ReconciliationMatch.active == True,  # noqa: E712
        )
    ).all()

    if any(m.economic_invoice_id == inv.id for m in existing_matches):
        raise HTTPException(
            status_code=422,
            detail="Denne faktura er allerede tilknyttet denne banktransaktion",
        )

    existing_total_ore = 0
    for m in existing_matches:
        ex_inv = session.get(EconomicInvoice, m.economic_invoice_id)
        if ex_inv:
            existing_total_ore += ex_inv.gross_amount_ore

    total_after = existing_total_ore + inv.gross_amount_ore
    if total_after > tx.amount_ore:
        remaining = tx.amount_ore - existing_total_ore
        raise HTTPException(
            status_code=422,
            detail=(
                f"Fakturabeløb {inv.gross_amount_ore / 100:.2f} kr overstiger restbeløbet "
                f"{remaining / 100:.2f} kr på banktransaktionen "
                f"(transaktion {tx.amount_ore / 100:.2f} kr, allerede matchet {existing_total_ore / 100:.2f} kr)"
            ),
        )

    match = ReconciliationMatch(
        bank_transaction_id=tx.id,
        economic_invoice_id=inv.id,
        match_type=MatchType.manual,
        confirmed=True,
        notes=body.notes,
    )
    inv.status = EconomicInvoiceStatus.matched
    session.add(match)
    session.add(inv)
    session.flush()

    if total_after == tx.amount_ore:
        tx.status = BankTransactionStatus.matched
        session.add(tx)

    session.commit()
    session.refresh(match)
    return ReconciliationMatchRead.model_validate(match, from_attributes=True)


# ── 3. GET /reconciliation/ ───────────────────────────────────────────────────

@router.get("/", response_model=ReconciliationViewRead)
def list_reconciliation(
    ctx: CompanyContextDep,
    status: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    active_only: bool = True,
) -> ReconciliationViewRead:
    """Invoice-centric combined view with match status and orphan transactions."""
    session = ctx.session
    company_id = ctx.company_id

    invoices_q = select(EconomicInvoice).where(EconomicInvoice.company_id == company_id)
    if active_only:
        invoices_q = invoices_q.where(EconomicInvoice.active == True)  # noqa: E712
    if date_from:
        invoices_q = invoices_q.where(EconomicInvoice.invoice_date >= date_from)
    if date_to:
        invoices_q = invoices_q.where(EconomicInvoice.invoice_date <= date_to)
    invoices = session.exec(invoices_q).all()

    invoice_ids = {inv.id for inv in invoices}
    matches: list[ReconciliationMatch] = []
    if invoice_ids:
        matches = session.exec(
            select(ReconciliationMatch).where(
                ReconciliationMatch.economic_invoice_id.in_(invoice_ids),
                ReconciliationMatch.active == True,  # noqa: E712
            )
        ).all()

    match_by_invoice: dict[str, ReconciliationMatch] = {
        m.economic_invoice_id: m for m in matches
    }
    tx_ids_needed = {m.bank_transaction_id for m in matches}
    txs: dict[str, BankTransaction] = {}
    if tx_ids_needed:
        for tx in session.exec(
            select(BankTransaction).where(BankTransaction.id.in_(tx_ids_needed))
        ).all():
            txs[tx.id] = tx

    today = date.today()
    items: list[ReconciliationItemRead] = []
    for inv in invoices:
        inv_read = _invoice_read(inv)
        match = match_by_invoice.get(inv.id)
        match_read = (
            ReconciliationMatchRead.model_validate(match, from_attributes=True)
            if match
            else None
        )
        tx = txs.get(match.bank_transaction_id) if match else None
        tx_read = BankTransactionRead.from_orm(tx) if tx else None

        if match and match.confirmed:
            rec_status = "matched"
        elif match and not match.confirmed:
            rec_status = "proposed"
        elif inv.status == EconomicInvoiceStatus.unmatched and inv.due_date < today:
            rec_status = "overdue"
        else:
            rec_status = "unmatched"

        if status and rec_status != status:
            continue

        items.append(
            ReconciliationItemRead(
                economic_invoice=inv_read,
                match=match_read,
                bank_transaction=tx_read,
                reconciliation_status=rec_status,
            )
        )

    matched_tx_ids = {m.bank_transaction_id for m in matches}
    orphan_q = select(BankTransaction).where(
        BankTransaction.company_id == company_id,
        BankTransaction.status == BankTransactionStatus.unmatched,
        BankTransaction.active == True,  # noqa: E712
    )
    orphan_txs = [
        tx for tx in session.exec(orphan_q).all()
        if tx.id not in matched_tx_ids
    ]
    orphan_reads = [BankTransactionRead.from_orm(tx) for tx in orphan_txs]

    return ReconciliationViewRead(items=items, orphan_transactions=orphan_reads)


# ── 4. GET /reconciliation/bank-view ─────────────────────────────────────────

@router.get("/bank-view", response_model=BankViewRead)
def bank_view(
    ctx: CompanyContextDep,
    active_only: bool = True,
) -> BankViewRead:
    """Bank-centric view: all bank transactions newest-first, each with active matches."""
    session = ctx.session
    company_id = ctx.company_id

    txs_q = select(BankTransaction).where(BankTransaction.company_id == company_id)
    if active_only:
        txs_q = txs_q.where(BankTransaction.active == True)  # noqa: E712
    txs_q = txs_q.order_by(BankTransaction.transaction_date.desc())
    txs = session.exec(txs_q).all()

    tx_ids = {tx.id for tx in txs}
    all_matches: list[ReconciliationMatch] = []
    if tx_ids:
        all_matches = session.exec(
            select(ReconciliationMatch).where(
                ReconciliationMatch.bank_transaction_id.in_(tx_ids),
                ReconciliationMatch.active == True,  # noqa: E712
            )
        ).all()

    matches_by_tx: dict[str, list[ReconciliationMatch]] = {}
    for m in all_matches:
        matches_by_tx.setdefault(m.bank_transaction_id, []).append(m)

    inv_ids = {m.economic_invoice_id for m in all_matches}
    invoices: dict[str, EconomicInvoice] = {}
    if inv_ids:
        for inv in session.exec(select(EconomicInvoice).where(EconomicInvoice.id.in_(inv_ids))).all():
            invoices[inv.id] = inv

    matched_count = proposed_count = unmatched_count = 0
    rows: list[BankTransactionWithMatchesRead] = []

    for tx in txs:
        tx_matches = matches_by_tx.get(tx.id, [])
        pairs: list[InvoiceMatchPairRead] = []
        for m in tx_matches:
            inv = invoices.get(m.economic_invoice_id)
            if inv:
                pairs.append(InvoiceMatchPairRead(
                    invoice=_invoice_read(inv),
                    match=ReconciliationMatchRead.model_validate(m, from_attributes=True),
                ))

        if tx_matches and all(m.confirmed for m in tx_matches):
            bank_status = "matched"
            matched_count += 1
        elif tx_matches:
            bank_status = "proposed"
            proposed_count += 1
        else:
            bank_status = "unmatched"
            unmatched_count += 1

        rows.append(BankTransactionWithMatchesRead(
            transaction=BankTransactionRead.from_orm(tx),
            matches=pairs,
            bank_status=bank_status,
        ))

    return BankViewRead(
        rows=rows,
        stats={
            "total": len(txs),
            "matched": matched_count,
            "proposed": proposed_count,
            "unmatched": unmatched_count,
        },
    )


# ── 5. POST /reconciliation/confirm-all ──────────────────────────────────────

@router.post("/confirm-all", response_model=ConfirmAllResult, status_code=200)
def confirm_all_balanced(ctx: CompanyContextDep) -> ConfirmAllResult:
    """Confirm all proposed matches where the invoice sum equals the bank transaction amount."""
    session = ctx.session
    company_id = ctx.company_id

    unconfirmed = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.active == True,  # noqa: E712
            ReconciliationMatch.confirmed == False,  # noqa: E712
        )
    ).all()

    tx_cache: dict[str, BankTransaction] = {}
    company_matches: list[ReconciliationMatch] = []
    for m in unconfirmed:
        if m.bank_transaction_id not in tx_cache:
            tx = session.get(BankTransaction, m.bank_transaction_id)
            if tx:
                tx_cache[m.bank_transaction_id] = tx
        tx = tx_cache.get(m.bank_transaction_id)
        if tx and tx.company_id == company_id:
            company_matches.append(m)

    groups: dict[str, list[ReconciliationMatch]] = {}
    for m in company_matches:
        groups.setdefault(m.bank_transaction_id, []).append(m)

    confirmed_matches = 0
    confirmed_transactions = 0
    skipped_transactions = 0

    for tx_id, group_matches in groups.items():
        tx = tx_cache[tx_id]

        inv_cache: dict[str, EconomicInvoice] = {}
        for m in group_matches:
            inv = session.get(EconomicInvoice, m.economic_invoice_id)
            if inv:
                inv_cache[m.economic_invoice_id] = inv

        total_ore = sum(
            inv_cache[m.economic_invoice_id].gross_amount_ore
            for m in group_matches
            if m.economic_invoice_id in inv_cache
        )

        if total_ore != tx.amount_ore:
            skipped_transactions += 1
            continue

        for m in group_matches:
            m.confirmed = True
            session.add(m)
            inv = inv_cache.get(m.economic_invoice_id)
            if inv:
                inv.status = EconomicInvoiceStatus.matched
                session.add(inv)
            confirmed_matches += 1

        tx.status = BankTransactionStatus.matched
        session.add(tx)
        confirmed_transactions += 1

    session.commit()
    return ConfirmAllResult(
        confirmed_matches=confirmed_matches,
        confirmed_transactions=confirmed_transactions,
        skipped_transactions=skipped_transactions,
    )


# ── 6. POST /reconciliation/{match_id}/confirm ───────────────────────────────

@router.post("/{match_id}/confirm", response_model=ReconciliationMatchRead)
def confirm_match(match_id: str, ctx: CompanyContextDep) -> ReconciliationMatchRead:
    """Confirm a proposed match (auto_ai, auto_number)."""
    session = ctx.session
    match = session.get(ReconciliationMatch, match_id)
    if not match or not match.active:
        raise HTTPException(status_code=404, detail=f"Match '{match_id}' ikke fundet")

    tx = session.get(BankTransaction, match.bank_transaction_id)
    if not tx:
        raise HTTPException(
            status_code=422,
            detail=f"BankTransaction '{match.bank_transaction_id}' ikke fundet",
        )
    if tx.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    inv = session.get(EconomicInvoice, match.economic_invoice_id)
    if not inv:
        raise HTTPException(
            status_code=422,
            detail=f"EconomicInvoice '{match.economic_invoice_id}' ikke fundet",
        )

    match.confirmed = True
    inv.status = EconomicInvoiceStatus.matched
    session.add(match)
    session.add(inv)
    session.flush()

    all_tx_matches = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.bank_transaction_id == tx.id,
            ReconciliationMatch.active == True,  # noqa: E712
        )
    ).all()
    if all(m.confirmed for m in all_tx_matches):
        tx.status = BankTransactionStatus.matched
        session.add(tx)

    session.commit()
    session.refresh(match)
    return ReconciliationMatchRead.model_validate(match, from_attributes=True)


# ── 7. POST /reconciliation/{match_id}/reject ────────────────────────────────

@router.post("/{match_id}/reject", response_model=ReconciliationMatchRead)
def reject_match(match_id: str, ctx: CompanyContextDep) -> ReconciliationMatchRead:
    """Reject (soft-delete) a match and revert invoice to unmatched."""
    session = ctx.session
    match = session.get(ReconciliationMatch, match_id)
    if not match or not match.active:
        raise HTTPException(status_code=404, detail=f"Match '{match_id}' ikke fundet")

    tx = session.get(BankTransaction, match.bank_transaction_id)
    if not tx:
        raise HTTPException(
            status_code=422,
            detail=f"BankTransaction '{match.bank_transaction_id}' ikke fundet",
        )
    if tx.company_id != ctx.company_id:
        raise HTTPException(status_code=403, detail="Adgang nægtet.")
    inv = session.get(EconomicInvoice, match.economic_invoice_id)
    if not inv:
        raise HTTPException(
            status_code=422,
            detail=f"EconomicInvoice '{match.economic_invoice_id}' ikke fundet",
        )

    remaining = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.bank_transaction_id == tx.id,
            ReconciliationMatch.active == True,  # noqa: E712
            ReconciliationMatch.id != match_id,
        )
    ).all()

    match.active = False
    inv.status = EconomicInvoiceStatus.unmatched
    session.add(match)
    session.add(inv)

    if not remaining:
        tx.status = BankTransactionStatus.unmatched
        session.add(tx)

    session.commit()
    session.refresh(match)
    return ReconciliationMatchRead.model_validate(match, from_attributes=True)
