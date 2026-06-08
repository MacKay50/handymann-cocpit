"""Wizard API: CVR lookup proxy and suggestion endpoint."""
from __future__ import annotations

import json
import logging
import re
from typing import Optional
from urllib import parse, request

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..dependencies import CompanyContextDep
from ..services import local_ai
from ..services.offer_search import keyword_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wizard", tags=["wizard"])


def _strip_and_parse(raw: str) -> Optional[dict]:
    """Strip markdown code fences then JSON-parse. Returns None on failure."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None

_CVR_TIMEOUT = 5


class CvrLookupRequest(BaseModel):
    cvr_number: str = Field(max_length=12)


class CvrLookupResponse(BaseModel):
    name: str
    address: str
    phone: str
    looked_up: bool


@router.post("/cvr-lookup")
def cvr_lookup(
    data: CvrLookupRequest, ctx: CompanyContextDep
) -> CvrLookupResponse:
    """Proxy to cvrapi.dk. Degrades to empty fields on any failure — never raises."""
    _company_id = ctx.company_id  # validates session; not used in the CVR call
    encoded_cvr = parse.quote(str(data.cvr_number), safe="")
    url = f"https://cvrapi.dk/api?search={encoded_cvr}&country=dk"
    try:
        with request.urlopen(url, timeout=_CVR_TIMEOUT) as resp:
            payload = json.loads(resp.read())
        name: str = payload["name"]
        address: Optional[str] = payload.get("address")
        if not address:
            city = payload.get("city", "")
            zipcode = payload.get("zipcode", "")
            address = f"{zipcode} {city}".strip()
        phone: str = payload.get("phone", "")
        return CvrLookupResponse(
            name=name, address=address or "", phone=phone, looked_up=True
        )
    except Exception as exc:  # URLError, JSONDecodeError, KeyError, timeout — any failure degrades
        logger.warning("CVR lookup failed for %s: %s", data.cvr_number, exc)
        return CvrLookupResponse(name="", address="", phone="", looked_up=False)


# ── POST /wizard/suggestions ──────────────────────────────────────────────────


class SuggestionsRequest(BaseModel):
    work_type: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)


class SuggestedLine(BaseModel):
    description: str
    unit: str          # e.g. "time", "m2", "stk"
    unit_price: float
    source: str        # "history" or "ai"


class SuggestionsResponse(BaseModel):
    suggested_lines: list[SuggestedLine]
    ai_used: bool
    matched_offers_count: int


@router.post("/suggestions", response_model=SuggestionsResponse)
def get_suggestions(
    data: SuggestionsRequest,
    ctx: CompanyContextDep,
) -> SuggestionsResponse:
    """Return suggested quote lines from keyword search + optional AI."""
    session = ctx.session
    company_id = ctx.company_id

    keyword_results = keyword_search(
        session=session,
        company_id=company_id,
        query=data.work_type,
        job_type=data.work_type,
    )

    lines: list[SuggestedLine] = []
    seen_descriptions: set[str] = set()

    for offer in keyword_results:
        if len(lines) >= 5:
            break
        if offer.treatment:
            desc = offer.treatment[:200]
            key = desc.lower()
            if key not in seen_descriptions:
                seen_descriptions.add(key)
                lines.append(SuggestedLine(
                    description=desc,
                    unit="time",
                    unit_price=offer.estimated_hours or 0.0,
                    source="history",
                ))
        if len(lines) >= 5:
            break
        if offer.materials:
            desc = offer.materials[:200]
            key = desc.lower()
            if key not in seen_descriptions:
                seen_descriptions.add(key)
                lines.append(SuggestedLine(
                    description=desc,
                    unit="stk",
                    unit_price=0.0,
                    source="history",
                ))

    ai_used = False
    if local_ai.is_enabled() and data.description is not None:
        prompt = (
            f"Jobtype: {data.work_type}\n"
            f"Beskrivelse: {data.description}\n\n"
            "Returner 3 tilbudslinjer som JSON-array: "
            '[{"description": "...", "unit": "time|m2|stk", "unit_price": float}]'
        )
        ai_raw = local_ai.chat_completion(
            prompt=prompt,
            system="Du er en hjælpsom håndværkerassistent. Returner KUN JSON.",
        )
        if ai_raw is not None:
            ai_items = _strip_and_parse(ai_raw)
            if ai_items is not None and not isinstance(ai_items, list):
                ai_items = None
            if ai_items is None:
                logger.warning("AI suggestion response was not valid JSON array: %.80s", ai_raw)
            if isinstance(ai_items, list):
                ai_used = True
                for item in ai_items:
                    if len(lines) >= 5:
                        break
                    try:
                        desc = str(item["description"])
                        key = desc.lower()
                        if key in seen_descriptions:
                            continue
                        seen_descriptions.add(key)
                        lines.append(SuggestedLine(
                            description=desc,
                            unit=str(item.get("unit", "time")),
                            unit_price=float(item.get("unit_price", 0.0)),
                            source="ai",
                        ))
                    except (KeyError, TypeError, ValueError) as exc:
                        logger.warning("Skipping malformed AI suggestion item: %s — %s", item, exc)

    return SuggestionsResponse(
        suggested_lines=lines,
        ai_used=ai_used,
        matched_offers_count=len(keyword_results),
    )


# ── POST /wizard/ai-draft ─────────────────────────────────────────────────────


class AiDraftRequest(BaseModel):
    task_type: str = Field(min_length=1, max_length=200)
    customer_name: Optional[str] = Field(default=None, max_length=200)
    address: Optional[str] = Field(default=None, max_length=500)
    job_notes: Optional[str] = Field(default=None, max_length=2000)


class AiDraftResponse(BaseModel):
    short_summary: str
    detailed_description: str
    ai_used: bool


@router.post("/ai-draft", response_model=AiDraftResponse)
def ai_draft(data: AiDraftRequest, ctx: CompanyContextDep) -> AiDraftResponse:
    """Generate a project description draft via local AI. Degrades gracefully if Ollama is unavailable."""
    _company_id = ctx.company_id  # validates session

    if not local_ai.is_enabled():
        return AiDraftResponse(short_summary="", detailed_description="", ai_used=False)

    context_parts = [f"Opgavetype: {data.task_type}"]
    if data.customer_name:
        context_parts.append(f"Kundenavn: {data.customer_name}")
    if data.address:
        context_parts.append(f"Adresse: {data.address}")
    if data.job_notes and data.job_notes.strip():
        context_parts.append(f"Notater om opgaven:\n{data.job_notes.strip()}")

    prompt = (
        "\n".join(context_parts) + "\n\n"
        "Skriv en professionel projektbeskrivelse til et håndværkertilbud som JSON. "
        "Brug KUN de faktiske oplysninger fra notaterne — gæt ikke på detaljer der ikke fremgår.\n"
        '{"short_summary": "Én kort sætning (max 100 tegn)", '
        '"detailed_description": "2-4 sætninger med konkrete detaljer fra notaterne"}'
    )

    raw = local_ai.chat_completion(
        prompt=prompt,
        system="Du er en professionel dansk håndværkerassistent. Returner KUN det JSON-objekt, ingen anden tekst.",
    )
    if raw is None:
        logger.warning("AI draft returned None for task_type=%s", data.task_type)
        return AiDraftResponse(short_summary="", detailed_description="", ai_used=False)

    parsed = _strip_and_parse(raw)
    if parsed is None:
        logger.warning("AI draft invalid JSON: %.80s", raw)
        return AiDraftResponse(short_summary="", detailed_description="", ai_used=False)

    short = str(parsed.get("short_summary", "")).strip()[:200]
    dd_raw = parsed.get("detailed_description", "")
    if isinstance(dd_raw, list):
        dd = " ".join(str(s) for s in dd_raw).strip()
    else:
        dd = str(dd_raw).strip()
    return AiDraftResponse(short_summary=short, detailed_description=dd[:1000], ai_used=True)


# ── POST /wizard/ai-draft-stream ──────────────────────────────────────────────


def _build_draft_context(data: AiDraftRequest) -> tuple[str, str]:
    """Return (prompt, system) for the streaming plain-text format."""
    parts = [f"Opgavetype: {data.task_type}"]
    if data.customer_name:
        parts.append(f"Kundenavn: {data.customer_name}")
    if data.address:
        parts.append(f"Adresse: {data.address}")
    if data.job_notes and data.job_notes.strip():
        parts.append(f"Notater om opgaven:\n{data.job_notes.strip()}")

    prompt = (
        "\n".join(parts) + "\n\n"
        "Skriv en professionel projektbeskrivelse til et håndværkertilbud.\n"
        "Brug KUN de faktiske oplysninger fra notaterne — gæt ikke på detaljer der ikke fremgår.\n\n"
        "Format (følg præcist, ingen ekstra tekst):\n"
        "Opsummering: [én kort sætning, max 100 tegn]\n"
        "Beskrivelse: [2-4 sætninger med konkrete detaljer]"
    )
    system = (
        "Du er en professionel dansk håndværkerassistent. "
        "Svar KUN i det angivne format — ingen ekstra forklaringer eller markdown."
    )
    return prompt, system


def _parse_plain_draft(text: str) -> tuple[str, str]:
    """Extract Opsummering / Beskrivelse from plain-text AI output."""
    m_sum = re.search(r"Opsummering:\s*(.+?)(?:\n|$)", text)
    m_desc = re.search(r"Beskrivelse:\s*([\s\S]+)", text)
    short = m_sum.group(1).strip()[:200] if m_sum else ""
    desc = m_desc.group(1).strip()[:1000] if m_desc else ""
    return short, desc


@router.post("/ai-draft-stream")
def ai_draft_stream(data: AiDraftRequest, ctx: CompanyContextDep) -> StreamingResponse:
    """SSE endpoint — streams tokens as they arrive, ends with a done event.

    Each event:  data: {"t": "<token>"}
    Final event: data: {"done": true, "short_summary": "...", "detailed_description": "...", "ai_used": true/false}
    """
    _company_id = ctx.company_id

    if not local_ai.is_enabled():
        def _empty():
            yield f"data: {json.dumps({'done': True, 'short_summary': '', 'detailed_description': '', 'ai_used': False})}\n\n"
        return StreamingResponse(_empty(), media_type="text/event-stream")

    prompt, system = _build_draft_context(data)

    def generate():
        accumulated = ""
        had_tokens = False
        for token in local_ai.stream_chat_completion(prompt, system=system):
            had_tokens = True
            accumulated += token
            yield f"data: {json.dumps({'t': token})}\n\n"

        short, desc = _parse_plain_draft(accumulated) if had_tokens else ("", "")
        yield f"data: {json.dumps({'done': True, 'short_summary': short, 'detailed_description': desc, 'ai_used': had_tokens})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
