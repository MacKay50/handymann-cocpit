"""Tests for offer_search service functions."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from haandvaerker.models.historical_offer import (
    ExtractionStatus,
    HistoricalOffer,
    HistoricalOfferChunk,
)
from haandvaerker.services.offer_search import similarity_search


@pytest.fixture(name="db_session")
def db_session_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_offer(
    session: Session,
    company_id: str,
    title: str = "Test Offer",
) -> HistoricalOffer:
    """Create a minimal approved HistoricalOffer scoped to company_id."""
    offer = HistoricalOffer(
        id=str(uuid.uuid4()),
        source_file_path=f"/fake/{title}.txt",
        source_file_hash=str(uuid.uuid4()),
        title=title,
        company_id=company_id,
        extraction_status=ExtractionStatus.approved,
        active=True,
    )
    session.add(offer)
    session.flush()
    return offer


def _make_chunk_with_embedding(
    session: Session,
    offer_id: str,
    embedding: list[float],
) -> HistoricalOfferChunk:
    chunk = HistoricalOfferChunk(
        id=str(uuid.uuid4()),
        historical_offer_id=offer_id,
        chunk_text="some text",
        embedding_json=json.dumps(embedding),
    )
    session.add(chunk)
    session.flush()
    return chunk


def test_similarity_search_company_scoped(db_session: Session) -> None:
    """similarity_search filtered by company_id must NOT return offers from other companies."""
    company_a = str(uuid.uuid4())
    company_b = str(uuid.uuid4())

    offer_a = _make_offer(db_session, company_a, "Offer A")
    offer_b = _make_offer(db_session, company_b, "Offer B")

    embedding = [1.0, 0.0, 0.0]
    _make_chunk_with_embedding(db_session, offer_a.id, embedding)
    _make_chunk_with_embedding(db_session, offer_b.id, embedding)
    db_session.commit()

    results = similarity_search(db_session, embedding, limit=10, company_id=company_a)

    result_offer_ids = {offer.id for _, offer in results}
    assert offer_a.id in result_offer_ids, "Offer A (same company) must appear in results"
    assert offer_b.id not in result_offer_ids, "Offer B (other company) must NOT appear in results"


def test_similarity_search_returns_tuple_list(db_session: Session) -> None:
    """similarity_search returns list of (score, offer) tuples."""
    company_id = str(uuid.uuid4())
    offer = _make_offer(db_session, company_id, "Offer X")
    _make_chunk_with_embedding(db_session, offer.id, [1.0, 0.0])
    db_session.commit()

    results = similarity_search(db_session, [1.0, 0.0], limit=5, company_id=company_id)

    assert isinstance(results, list)
    assert len(results) == 1
    score, returned_offer = results[0]
    assert isinstance(score, float)
    assert returned_offer.id == offer.id


def test_similarity_search_no_results_for_other_company(db_session: Session) -> None:
    """When the only offers belong to company B, searching as company A returns nothing."""
    company_a = str(uuid.uuid4())
    company_b = str(uuid.uuid4())

    offer_b = _make_offer(db_session, company_b, "Offer B only")
    _make_chunk_with_embedding(db_session, offer_b.id, [1.0, 0.0])
    db_session.commit()

    results = similarity_search(db_session, [1.0, 0.0], limit=10, company_id=company_a)
    assert results == []
