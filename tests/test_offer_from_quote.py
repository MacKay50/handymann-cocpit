"""Tests for Phase 4: auto-create HistoricalOffer when a quote is accepted.

Covers all acceptance criteria:
  AC-1  accept_quote (staff) creates exactly one HistoricalOffer with correct fields
  AC-2  accept_by_token (public) creates HistoricalOffer via the shared function
  AC-3  idempotent on quote_id — repeated call returns the existing record, no duplicate
  AC-4  area-based quote fills area_m2 from rooms; line-based leaves it None
  AC-5  created HistoricalOffer appears in GET /historical-offers
  AC-6  if create_historical_offer_from_quote raises, accept still completes (error logged)
"""
from __future__ import annotations
import logging
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from haandvaerker.models.historical_offer import HistoricalOffer


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_line_quote(client: TestClient) -> dict:
    """customer → project → line-based quote (sent) — returns {quote_id, token}."""
    cust = client.post("/customers/", json={"name": "Testfirma"}).json()
    proj = client.post("/projects/", json={
        "customer_id": cust["id"],
        "title": "Malerarbejde",
        "status": "draft",
    }).json()
    quote = client.post("/quotes/", json={
        "project_id": proj["id"],
        "title": "Tilbud maling",
        "quote_type": "line",
        "lines": [
            {"description": "Stue", "unit": "m2", "quantity": 20, "unit_price": 100},
            {"description": "Soveværelse", "unit": "m2", "quantity": 10, "unit_price": 100},
        ],
    }).json()
    sent = client.post(f"/quotes/{quote['id']}/send").json()
    return {"quote_id": quote["id"], "token": sent["accept_token"]}


def _make_area_quote(client: TestClient) -> dict:
    """customer → project → area-based quote (sent) — returns {quote_id, token}."""
    cust = client.post("/customers/", json={"name": "Arealfirma"}).json()
    proj = client.post("/projects/", json={
        "customer_id": cust["id"],
        "title": "Vinduesareal projekt",
        "status": "draft",
    }).json()
    quote = client.post("/quotes/", json={
        "project_id": proj["id"],
        "title": "Areal tilbud",
        "quote_type": "area",
        "rooms": [
            {"name": "Stue", "length_m": 5.0, "width_m": 4.0, "height_m": 2.5,
             "window_m2": 2.0, "door_m2": 1.8, "price_per_m2": 50.0},
            {"name": "Køkken", "length_m": 3.0, "width_m": 3.0, "height_m": 2.5,
             "window_m2": 1.0, "door_m2": 0.0, "price_per_m2": 60.0},
        ],
    }).json()
    sent = client.post(f"/quotes/{quote['id']}/send").json()
    return {"quote_id": quote["id"], "token": sent["accept_token"]}


# ── AC-1: staff accept creates HistoricalOffer with correct fields ───────────

def test_staff_accept_creates_historical_offer(client: TestClient, session: Session):
    ctx = _make_line_quote(client)
    r = client.post(f"/quotes/{ctx['quote_id']}/accept")
    assert r.status_code == 200

    offers = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == ctx["quote_id"])
    ).all()
    assert len(offers) == 1
    offer = offers[0]
    assert offer.extraction_status == "approved"
    assert offer.accepted_status == "accepted"
    assert offer.quote_id == ctx["quote_id"]


def test_staff_accept_prices_match_quote(client: TestClient, session: Session):
    ctx = _make_line_quote(client)
    quote_data = client.get(f"/quotes/{ctx['quote_id']}").json()
    r = client.post(f"/quotes/{ctx['quote_id']}/accept")
    assert r.status_code == 200

    offer = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == ctx["quote_id"])
    ).first()
    assert offer is not None
    assert offer.price_ex_vat == quote_data["subtotal"]
    assert offer.vat == quote_data["vat_amount"]
    assert offer.price_inc_vat == quote_data["total"]


def test_staff_accept_sets_company_id(client: TestClient, session: Session, company_id: str):
    ctx = _make_line_quote(client)
    client.post(f"/quotes/{ctx['quote_id']}/accept")

    offer = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == ctx["quote_id"])
    ).first()
    assert offer is not None
    assert offer.company_id == company_id


# ── AC-2: accept_by_token uses same shared function ──────────────────────────

def test_token_accept_creates_historical_offer(client: TestClient, session: Session):
    ctx = _make_line_quote(client)
    r = client.post(f"/quotes/by-token/{ctx['token']}/accept")
    assert r.status_code == 200

    offers = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == ctx["quote_id"])
    ).all()
    assert len(offers) == 1
    offer = offers[0]
    assert offer.extraction_status == "approved"
    assert offer.accepted_status == "accepted"


def test_token_accept_prices_match_quote(client: TestClient, session: Session):
    ctx = _make_line_quote(client)
    quote_data = client.get(f"/quotes/{ctx['quote_id']}").json()
    client.post(f"/quotes/by-token/{ctx['token']}/accept")

    offer = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == ctx["quote_id"])
    ).first()
    assert offer is not None
    assert offer.price_ex_vat == quote_data["subtotal"]
    assert offer.vat == quote_data["vat_amount"]
    assert offer.price_inc_vat == quote_data["total"]


# ── AC-3: idempotent — repeated accept does NOT create duplicate ─────────────

def test_idempotent_on_repeated_service_call(session: Session):
    """Call create_historical_offer_from_quote twice with the same quote_id."""
    import uuid
    from haandvaerker.models.quote import Quote
    from haandvaerker.services.offer_from_quote import create_historical_offer_from_quote

    # Build a minimal quote object (not persisted — we only need its fields)
    company_id = str(uuid.uuid4())
    quote = Quote(
        id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        company_id=company_id,
        quote_number="TIL-2026-001",
        title="Idempotenst test",
        quote_type="line",
        subtotal=1000.0,
        vat_amount=250.0,
        total=1250.0,
    )
    session.add(quote)
    session.commit()

    o1 = create_historical_offer_from_quote(session, quote)
    session.add(o1)
    session.commit()

    o2 = create_historical_offer_from_quote(session, quote)
    session.add(o2)
    session.commit()

    count = len(
        session.exec(
            select(HistoricalOffer).where(HistoricalOffer.quote_id == quote.id)
        ).all()
    )
    assert count == 1
    assert o1.id == o2.id


# ── AC-4: area-based fills area_m2; line-based leaves it None ────────────────

def test_area_quote_fills_area_m2(client: TestClient, session: Session):
    ctx = _make_area_quote(client)
    client.post(f"/quotes/{ctx['quote_id']}/accept")

    offer = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == ctx["quote_id"])
    ).first()
    assert offer is not None
    # Stue: 5*4 = 20 m2, Køkken: 3*3 = 9 m2 → total 29 m2
    assert offer.area_m2 == pytest.approx(29.0)


def test_line_quote_leaves_area_m2_none(client: TestClient, session: Session):
    ctx = _make_line_quote(client)
    client.post(f"/quotes/{ctx['quote_id']}/accept")

    offer = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == ctx["quote_id"])
    ).first()
    assert offer is not None
    assert offer.area_m2 is None


# ── AC-5: HistoricalOffer appears in GET /historical-offers ──────────────────

def test_accepted_offer_appears_in_list(client: TestClient, session: Session):
    ctx = _make_line_quote(client)
    client.post(f"/quotes/{ctx['quote_id']}/accept")

    # The GET endpoint filters by company (via CompanyContextDep)
    # but HistoricalOffer.company_id is set so it should appear
    r = client.get("/historical-offers/")
    assert r.status_code == 200
    offer_ids = [o["id"] for o in r.json()]

    db_offer = session.exec(
        select(HistoricalOffer).where(HistoricalOffer.quote_id == ctx["quote_id"])
    ).first()
    assert db_offer is not None
    assert db_offer.id in offer_ids


# ── AC-6: if service raises, accept still completes; error is logged ─────────

def test_staff_accept_survives_service_error(client: TestClient, caplog):
    ctx = _make_line_quote(client)

    with patch(
        "haandvaerker.api.quotes.create_historical_offer_from_quote",
        side_effect=RuntimeError("erfaringsbank boom"),
    ), caplog.at_level(logging.ERROR):
        r = client.post(f"/quotes/{ctx['quote_id']}/accept")

    assert r.status_code == 200  # accept must still succeed
    assert r.json()["status"] == "accepted"
    assert any("erfaringsbank" in m.lower() or "boom" in m.lower() for m in caplog.messages)


def test_token_accept_survives_service_error(client: TestClient, caplog):
    ctx = _make_line_quote(client)

    with patch(
        "haandvaerker.api.quotes.create_historical_offer_from_quote",
        side_effect=RuntimeError("erfaringsbank boom"),
    ), caplog.at_level(logging.ERROR):
        r = client.post(f"/quotes/by-token/{ctx['token']}/accept")

    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    assert any("erfaringsbank" in m.lower() or "boom" in m.lower() for m in caplog.messages)


# ── Service unit tests ────────────────────────────────────────────────────────

def test_service_title_from_quote_title(session: Session):
    import uuid
    from haandvaerker.models.quote import Quote
    from haandvaerker.services.offer_from_quote import create_historical_offer_from_quote

    quote = Quote(
        id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
        company_id=str(uuid.uuid4()),
        quote_number="TIL-2026-002",
        title="Malerarbejde villa",
        quote_type="line",
        subtotal=5000.0,
        vat_amount=1250.0,
        total=6250.0,
    )
    session.add(quote)
    session.commit()

    offer = create_historical_offer_from_quote(session, quote)
    assert offer.title == "Malerarbejde villa"
