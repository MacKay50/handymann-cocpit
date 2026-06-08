from __future__ import annotations
import json
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.historical_offer import (
    ComparisonReportRead,
    HistoricalComparisonReport,
    HistoricalOfferRead,
)
from ..services.local_ai import generate_embeddings, is_enabled as ai_enabled
from ..services.offer_search import compute_price_stats, keyword_search, similarity_search

router = APIRouter(prefix="/historical-comparisons", tags=["historical-comparisons"])


def _report_to_read(
    report: HistoricalComparisonReport,
    offers: Optional[list[HistoricalOfferRead]] = None,
) -> ComparisonReportRead:
    try:
        matched_ids: list[str] = json.loads(report.matched_offer_ids_json)
    except (json.JSONDecodeError, TypeError):
        matched_ids = []
    try:
        suggested_qs: list[str] = json.loads(report.suggested_questions_json) if report.suggested_questions_json else []
    except (json.JSONDecodeError, TypeError):
        suggested_qs = []
    return ComparisonReportRead(
        id=report.id,
        quote_preparation_id=report.quote_preparation_id,
        query_summary=report.query_summary,
        matched_offer_ids=matched_ids,
        price_range_low=report.price_range_low,
        price_range_median=report.price_range_median,
        price_range_high=report.price_range_high,
        price_per_m2_low=report.price_per_m2_low,
        price_per_m2_median=report.price_per_m2_median,
        price_per_m2_high=report.price_per_m2_high,
        suggested_questions=suggested_qs,
        relevant_assumptions=report.relevant_assumptions,
        relevant_exclusions=report.relevant_exclusions,
        comparison_summary=report.comparison_summary,
        matched_offers=offers or [],
        active=report.active,
        created_at=report.created_at,
    )


@router.post("/search", response_model=ComparisonReportRead, status_code=201)
def search_similar(
    ctx: CompanyContextDep,
    query: str,
    job_type: Optional[str] = None,
    building_type: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    quote_preparation_id: Optional[str] = None,
) -> ComparisonReportRead:
    """Find similar historical offers and produce a comparison report."""
    from ..models.historical_offer import HistoricalOffer as HO
    session = ctx.session
    company_id = ctx.company_id

    keyword_matches = keyword_search(
        session, company_id, query, job_type, building_type, year_min, year_max
    )

    vector_matches: list[HO] = []
    if ai_enabled() and query.strip():
        embedding = generate_embeddings(query)
        if embedding:
            vector_matches = [o for _, o in similarity_search(session, embedding, company_id=company_id)]

    seen: set[str] = set()
    merged: list[HO] = []
    for o in keyword_matches + vector_matches:
        if o.id not in seen:
            seen.add(o.id)
            merged.append(o)

    stats = compute_price_stats(merged)
    matched_ids = [o.id for o in merged]

    assumptions = "\n---\n".join(
        o.assumptions for o in merged[:5] if o.assumptions
    ) or None
    exclusions = "\n---\n".join(
        o.exclusions for o in merged[:5] if o.exclusions
    ) or None

    now = datetime.utcnow()
    report = HistoricalComparisonReport(
        id=str(uuid.uuid4()),
        quote_preparation_id=quote_preparation_id,
        query_summary=query[:500] if query else None,
        matched_offer_ids_json=json.dumps(matched_ids),
        price_range_low=stats["price_range_low"],
        price_range_median=stats["price_range_median"],
        price_range_high=stats["price_range_high"],
        price_per_m2_low=stats["price_per_m2_low"],
        price_per_m2_median=stats["price_per_m2_median"],
        price_per_m2_high=stats["price_per_m2_high"],
        relevant_assumptions=assumptions,
        relevant_exclusions=exclusions,
        comparison_summary=f"Fandt {len(merged)} lignende tilbud.",
        created_at=now,
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    from ..api.historical_offers import _to_read
    offer_reads = [_to_read(o) for o in merged[:10]]
    return _report_to_read(report, offer_reads)


@router.get("/", response_model=list[ComparisonReportRead])
def list_reports(
    ctx: CompanyContextDep,
    quote_preparation_id: Optional[str] = None,
    active_only: bool = True,
) -> list[ComparisonReportRead]:
    session = ctx.session
    stmt = select(HistoricalComparisonReport)
    if active_only:
        stmt = stmt.where(HistoricalComparisonReport.active == True)
    if quote_preparation_id:
        stmt = stmt.where(
            HistoricalComparisonReport.quote_preparation_id == quote_preparation_id
        )
    return [_report_to_read(r) for r in session.exec(stmt).all()]


@router.get("/{report_id}", response_model=ComparisonReportRead)
def get_report(report_id: str, ctx: CompanyContextDep) -> ComparisonReportRead:
    session = ctx.session
    report = session.get(HistoricalComparisonReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="ComparisonReport not found")
    return _report_to_read(report)
