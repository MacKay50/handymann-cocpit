"""Tests for historical-comparisons API endpoints.

AC-7: Verify existing comparison behaviour still works after similarity_search
signature change (company_id is now required).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def test_search_returns_201_with_no_matches(client: TestClient) -> None:
    """POST /historical-comparisons/search with a query that matches nothing → 201 empty report."""
    r = client.post(
        "/historical-comparisons/search",
        params={"query": "ingen-match-xyz"},
    )
    assert r.status_code == 201, r.json()
    data = r.json()
    assert data["matched_offer_ids"] == []
    assert data["comparison_summary"] is not None


def test_search_similarity_path_passes_company_id(client: TestClient, company_id: str) -> None:
    """When AI is enabled, similarity_search is called with the session company_id.

    This verifies the updated call site in historical_comparisons.py passes
    company_id correctly — preventing cross-company data leak (CONT-10).
    """
    captured: dict = {}

    from haandvaerker.services.offer_search import similarity_search as real_ss

    def _capture(session, embedding, *, company_id="", **kw):  # type: ignore[misc]
        captured["company_id"] = company_id
        return real_ss(session, embedding, company_id=company_id, **kw)

    with patch("haandvaerker.api.historical_comparisons.ai_enabled", return_value=True), \
         patch("haandvaerker.api.historical_comparisons.generate_embeddings", return_value=[1.0, 0.0]), \
         patch("haandvaerker.api.historical_comparisons.similarity_search", side_effect=_capture):
        r = client.post(
            "/historical-comparisons/search",
            params={"query": "maling"},
        )

    assert r.status_code == 201, r.json()
    assert captured.get("company_id") == company_id, (
        f"similarity_search must receive company_id={company_id!r}, got {captured.get('company_id')!r}"
    )


def test_list_reports_returns_200(client: TestClient) -> None:
    """GET /historical-comparisons/ returns 200 and a list."""
    r = client.get("/historical-comparisons/")
    assert r.status_code == 200, r.json()
    assert isinstance(r.json(), list)


def test_get_report_not_found_returns_404(client: TestClient) -> None:
    """GET /historical-comparisons/{unknown-id} → 404."""
    r = client.get("/historical-comparisons/nonexistent-id")
    assert r.status_code == 404, r.json()
