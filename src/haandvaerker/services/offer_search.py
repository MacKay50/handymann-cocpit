"""Keyword/filter search + cosine similarity over HistoricalOffer + chunks."""
from __future__ import annotations
import json
import math
from typing import Optional

from sqlmodel import Session, select

from ..models.historical_offer import (
    ExtractionStatus,
    HistoricalOffer,
    HistoricalOfferChunk,
)


def keyword_search(
    session: Session,
    company_id: str,
    query: str,
    job_type: Optional[str] = None,
    building_type: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    limit: int = 20,
) -> list[HistoricalOffer]:
    """Return active, approved offers matching *query* text + optional filters."""
    stmt = select(HistoricalOffer).where(
        HistoricalOffer.active == True,
        HistoricalOffer.extraction_status == ExtractionStatus.approved,
    )
    if job_type:
        stmt = stmt.where(HistoricalOffer.job_type == job_type)
    if building_type:
        stmt = stmt.where(HistoricalOffer.building_type == building_type)
    if year_min:
        stmt = stmt.where(HistoricalOffer.year >= year_min)
    if year_max:
        stmt = stmt.where(HistoricalOffer.year <= year_max)

    offers = session.exec(stmt).all()
    if not query.strip():
        return list(offers)[:limit]

    lower_q = query.lower()
    scored: list[tuple[int, HistoricalOffer]] = []
    for offer in offers:
        score = _score_offer(offer, lower_q)
        if score > 0:
            scored.append((score, offer))

    # Also search chunks for more coverage
    chunk_offer_ids = _chunk_keyword_search(session, lower_q)
    chunk_set = set(chunk_offer_ids)
    for offer in offers:
        if offer.id in chunk_set and not any(o.id == offer.id for _, o in scored):
            scored.append((1, offer))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [o for _, o in scored[:limit]]


def _score_offer(offer: HistoricalOffer, lower_q: str) -> int:
    score = 0
    for field in (offer.title, offer.job_type, offer.building_type, offer.summary,
                  offer.treatment, offer.materials, offer.surface_condition):
        if field and lower_q in field.lower():
            score += 2
    if offer.assumptions and lower_q in offer.assumptions.lower():
        score += 1
    if offer.exclusions and lower_q in offer.exclusions.lower():
        score += 1
    return score


def _chunk_keyword_search(session: Session, lower_q: str) -> list[str]:
    chunks = session.exec(select(HistoricalOfferChunk)).all()
    ids: list[str] = []
    for chunk in chunks:
        if lower_q in chunk.chunk_text.lower():
            ids.append(chunk.historical_offer_id)
    return ids


def similarity_search(
    session: Session,
    query_embedding: list[float],
    limit: int = 10,
    *,
    company_id: str,
) -> list[tuple[float, HistoricalOffer]]:
    """Return top *limit* offers sorted by cosine similarity to *query_embedding*.

    Only chunks belonging to offers with matching company_id are considered.
    company_id is required — omitting it is a compile-time error.
    """

    chunks = session.exec(
        select(HistoricalOfferChunk)
        .join(HistoricalOffer, HistoricalOfferChunk.historical_offer_id == HistoricalOffer.id)  # type: ignore[arg-type]
        .where(
            HistoricalOfferChunk.embedding_json != None,  # noqa: E711
            HistoricalOffer.company_id == company_id,
        )
    ).all()

    scored: dict[str, float] = {}
    for chunk in chunks:
        try:
            vec = json.loads(chunk.embedding_json)  # type: ignore[arg-type]
        except (json.JSONDecodeError, TypeError):
            continue
        sim = _cosine(query_embedding, vec)
        oid = chunk.historical_offer_id
        if oid not in scored or sim > scored[oid]:
            scored[oid] = sim

    top_ids = sorted(scored, key=lambda k: scored[k], reverse=True)[:limit]
    results: list[tuple[float, HistoricalOffer]] = []
    for oid in top_ids:
        offer = session.get(HistoricalOffer, oid)
        if offer and offer.active:
            results.append((scored[oid], offer))
    return results


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def compute_price_stats(offers: list[HistoricalOffer]) -> dict:
    prices = sorted(o.price_ex_vat for o in offers if o.price_ex_vat is not None)
    per_m2 = sorted(
        o.price_ex_vat / o.area_m2
        for o in offers
        if o.price_ex_vat and o.area_m2
    )
    return {
        "price_range_low": prices[0] if prices else None,
        "price_range_median": _median(prices),
        "price_range_high": prices[-1] if prices else None,
        "price_per_m2_low": per_m2[0] if per_m2 else None,
        "price_per_m2_median": _median(per_m2),
        "price_per_m2_high": per_m2[-1] if per_m2 else None,
    }


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    n = len(values)
    mid = n // 2
    return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2
