"""Shared service: create a HistoricalOffer from an accepted Quote.

Single source of truth called from both accept paths (staff and public token).
"""
from __future__ import annotations

from sqlmodel import Session, select

from ..models.historical_offer import ExtractionStatus, HistoricalOffer
from ..models.quote import Quote, QuoteRoom


def create_historical_offer_from_quote(
    session: Session, quote: Quote
) -> HistoricalOffer:
    """Return (or create) a HistoricalOffer linked to *quote*.

    Idempotent: if a HistoricalOffer with this quote_id already exists, return
    it without creating a duplicate.

    Does NOT commit — the caller is responsible for committing.

    Field mapping (deterministic, no fabrication):
    - title         ← quote.title (always present)
    - price_ex_vat  ← quote.subtotal
    - vat           ← quote.vat_amount
    - price_inc_vat ← quote.total
    - area_m2       ← sum(length_m * width_m) for all rooms if quote_type=="area",
                      else None
    - extraction_status ← "approved"
    - accepted_status   ← "accepted"
    - company_id    ← quote.company_id
    - quote_id      ← quote.id
    - source_file_path / source_file_hash — sentinel values ("quote:<id>", "")
      to satisfy the NOT NULL constraints on those columns while making the
      provenance clear.
    """
    existing = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == quote.id)
    ).first()
    if existing is not None:
        return existing

    area_m2: float | None = None
    if quote.quote_type == "area":
        rooms = session.exec(
            select(QuoteRoom).where(QuoteRoom.quote_id == quote.id)
        ).all()
        if rooms:
            area_m2 = sum(r.length_m * r.width_m for r in rooms)

    offer = HistoricalOffer(
        company_id=quote.company_id,
        quote_id=quote.id,
        source_file_path=f"quote:{quote.id}",
        source_file_hash=f"quote:{quote.id}",
        title=quote.title,
        price_ex_vat=quote.subtotal,
        vat=quote.vat_amount,
        price_inc_vat=quote.total,
        area_m2=area_m2,
        extraction_status=ExtractionStatus.approved,
        accepted_status="accepted",
    )
    session.add(offer)
    return offer
