from __future__ import annotations

import pathlib
from datetime import date
from typing import Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..dependencies import CompanyContextDep
from ..models.bank_transaction import BankTransaction, BankTransactionRead, BankTransactionStatus
from ..models.economic_invoice import EconomicInvoice, EconomicInvoiceStatus
from ..models.reconciliation_match import ReconciliationMatch
from ..services.danish_csv import ImportResult, decode_csv_bytes, parse_danske_bank_csv

router = APIRouter(prefix="/bank-transactions", tags=["bank-transactions"])


# ── response models ────────────────────────────────────────────────────────────

class ClearPreviewResult(BaseModel):
    bank_transaction_count: int
    active_match_count: int
    confirmed_match_count: int
    warnings: list[str]


class ClearAllResult(BaseModel):
    deleted_bank_transactions: int
    deleted_matches: int
    invoices_reverted: int


# ── import endpoints ───────────────────────────────────────────────────────────

@router.post("/import", response_model=ImportResult, status_code=201)
def import_bank_transactions(
    file_path: str,
    ctx: CompanyContextDep,
) -> ImportResult:
    """Import Danske Bank CSV. All-or-nothing: if any row fails validation, 422 with error list."""
    session = ctx.session
    company_id = ctx.company_id

    p = pathlib.Path(file_path)
    if not p.exists():
        raise HTTPException(status_code=422, detail=f"Fil ikke fundet: {file_path}")
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        content = decode_csv_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rows, errors = parse_danske_bank_csv(content, company_id)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    for row in rows:
        tx = BankTransaction(**row.model_dump())
        session.add(tx)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Import indeholder allerede importerede rækker — ingen rækker er gemt. Ret CSV-filen og forsøg igen.",
        )

    return ImportResult(rows_imported=len(rows), rows_skipped=0, errors=[])


@router.post("/import-upload", response_model=ImportResult, status_code=201)
async def import_bank_transactions_upload(
    ctx: CompanyContextDep,
    file: UploadFile = File(...),
) -> ImportResult:
    """Import Danske Bank CSV via browser file upload. All-or-nothing."""
    session = ctx.session
    company_id = ctx.company_id
    raw = await file.read()
    try:
        content = decode_csv_bytes(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    rows, errors = parse_danske_bank_csv(content, company_id)
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    for row in rows:
        tx = BankTransaction(**row.model_dump())
        session.add(tx)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Import indeholder allerede importerede rækker — ingen rækker er gemt.",
        )
    return ImportResult(rows_imported=len(rows), rows_skipped=0, errors=[])


# ── list ───────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[BankTransactionRead])
def list_bank_transactions(
    ctx: CompanyContextDep,
    status: Optional[BankTransactionStatus] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    active_only: bool = True,
) -> list[BankTransactionRead]:
    """List bank transactions for the session company with optional filters."""
    session = ctx.session
    q = select(BankTransaction).where(BankTransaction.company_id == ctx.company_id)
    if active_only:
        q = q.where(BankTransaction.active == True)  # noqa: E712
    if status:
        q = q.where(BankTransaction.status == status)
    if date_from:
        q = q.where(BankTransaction.transaction_date >= date_from)
    if date_to:
        q = q.where(BankTransaction.transaction_date <= date_to)
    return [BankTransactionRead.from_orm(tx) for tx in session.exec(q).all()]


# ── clear (preview + execute) ──────────────────────────────────────────────────

@router.get("/clear-preview", response_model=ClearPreviewResult)
def clear_bank_preview(ctx: CompanyContextDep) -> ClearPreviewResult:
    """Return impact summary before clearing all bank transactions for the session company.

    Read-only — no data is changed.
    """
    session = ctx.session
    company_id = ctx.company_id

    txs = session.exec(
        select(BankTransaction).where(BankTransaction.company_id == company_id)
    ).all()
    if not txs:
        return ClearPreviewResult(
            bank_transaction_count=0, active_match_count=0, confirmed_match_count=0, warnings=[],
        )

    tx_ids = {tx.id for tx in txs}
    active_matches = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.bank_transaction_id.in_(tx_ids),
            ReconciliationMatch.active == True,  # noqa: E712
        )
    ).all()
    confirmed_count = sum(1 for m in active_matches if m.confirmed)

    warnings: list[str] = []
    if confirmed_count:
        warnings.append(f"{confirmed_count} bekræftede afstemninger vil gå tabt")
    if len(active_matches) - confirmed_count > 0:
        warnings.append(f"{len(active_matches) - confirmed_count} ubekræftede forslag fjernes")

    return ClearPreviewResult(
        bank_transaction_count=len(txs),
        active_match_count=len(active_matches),
        confirmed_match_count=confirmed_count,
        warnings=warnings,
    )


@router.post("/clear-all", response_model=ClearAllResult, status_code=200)
def clear_all_bank_transactions(ctx: CompanyContextDep) -> ClearAllResult:
    """Delete all bank transactions for the session company.

    Deactivates all related reconciliation matches and reverts invoice statuses
    to unmatched where no other active matches remain.
    """
    session = ctx.session
    company_id = ctx.company_id

    txs = session.exec(
        select(BankTransaction).where(BankTransaction.company_id == company_id)
    ).all()
    if not txs:
        return ClearAllResult(deleted_bank_transactions=0, deleted_matches=0, invoices_reverted=0)

    tx_ids = {tx.id for tx in txs}

    # All matches (active and inactive) referencing these transactions
    all_matches = session.exec(
        select(ReconciliationMatch).where(
            ReconciliationMatch.bank_transaction_id.in_(tx_ids)
        )
    ).all()

    # Invoices to revert: those whose only active matches point at our tx set
    inv_ids_to_check = {m.economic_invoice_id for m in all_matches if m.active}
    invoices_reverted = 0
    for inv_id in inv_ids_to_check:
        other_active = session.exec(
            select(ReconciliationMatch).where(
                ReconciliationMatch.economic_invoice_id == inv_id,
                ReconciliationMatch.active == True,  # noqa: E712
                ReconciliationMatch.bank_transaction_id.not_in(tx_ids),
            )
        ).first()
        if not other_active:
            inv = session.get(EconomicInvoice, inv_id)
            if inv and inv.status == EconomicInvoiceStatus.matched:
                inv.status = EconomicInvoiceStatus.unmatched
                session.add(inv)
                invoices_reverted += 1

    # Delete matches before transactions (FK safety)
    deleted_matches = len(all_matches)
    for m in all_matches:
        session.delete(m)
    session.flush()

    for tx in txs:
        session.delete(tx)

    session.commit()
    return ClearAllResult(
        deleted_bank_transactions=len(txs),
        deleted_matches=deleted_matches,
        invoices_reverted=invoices_reverted,
    )
