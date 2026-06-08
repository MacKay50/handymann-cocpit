from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from sqlmodel import select
from ..dependencies import CompanyContextDep
from ..models.historical_offer import (
    ExtractionStatus,
    HistoricalOffer,
    HistoricalOfferChunk,
    HistoricalOfferImportJob,
    HistoricalOfferRead,
    HistoricalOfferUpdate,
    ImportJobRead,
    ImportJobStatus,
    ChunkType,
)
from ..services.document_extractor import extract_text
from ..services.historical_offer_extractor import extract_offer_fields
from ..services.local_ai import generate_embeddings, is_enabled as ai_enabled

router = APIRouter(prefix="/historical-offers", tags=["historical-offers"])


def _to_read(offer: HistoricalOffer) -> HistoricalOfferRead:
    r = HistoricalOfferRead.model_validate(offer)
    if offer.price_ex_vat and offer.area_m2:
        r.price_per_m2 = round(offer.price_ex_vat / offer.area_m2, 2)
    return r


def _file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@router.post("/import", response_model=ImportJobRead, status_code=201)
def import_file(
    file_path: str,
    ctx: CompanyContextDep,
) -> ImportJobRead:
    """Start an import job for a local file. Returns job record immediately."""
    import pathlib
    session = ctx.session
    p = pathlib.Path(file_path)
    if not p.exists():
        raise HTTPException(status_code=422, detail=f"File not found: {file_path}")

    try:
        file_hash = _file_hash(file_path)
    except OSError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing_job = session.exec(
        select(HistoricalOfferImportJob).where(
            HistoricalOfferImportJob.file_hash == file_hash,
            HistoricalOfferImportJob.active == True,  # noqa: E712
        )
    ).first()
    if existing_job:
        return ImportJobRead.model_validate(existing_job)

    now = datetime.utcnow()
    job = HistoricalOfferImportJob(
        id=str(uuid.uuid4()),
        file_path=file_path,
        file_hash=file_hash,
        status=ImportJobStatus.processing,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    try:
        text = extract_text(file_path)
    except Exception as exc:  # noqa: BLE001
        job.status = ImportJobStatus.failed
        job.error_message = str(exc)[:1000]
        job.updated_at = datetime.utcnow()
        session.add(job)
        session.commit()
        session.refresh(job)
        return ImportJobRead.model_validate(job)

    job.extracted_text = text

    fields = extract_offer_fields(text)
    job.extracted_json = json.dumps(fields, ensure_ascii=False)

    offer = HistoricalOffer(
        id=str(uuid.uuid4()),
        source_file_path=file_path,
        source_file_hash=file_hash,
        extraction_status=ExtractionStatus.needs_review,
        **fields,
    )
    session.add(offer)
    session.flush()

    if text.strip():
        chunk = HistoricalOfferChunk(
            id=str(uuid.uuid4()),
            historical_offer_id=offer.id,
            chunk_text=text,
            chunk_type=ChunkType.extracted_text,
        )
        if ai_enabled():
            vec = generate_embeddings(text[:2000])
            if vec:
                chunk.embedding_json = json.dumps(vec)
        session.add(chunk)

    job.historical_offer_id = offer.id
    job.status = ImportJobStatus.needs_review
    job.updated_at = datetime.utcnow()
    session.add(job)
    session.commit()
    session.refresh(job)
    return ImportJobRead.model_validate(job)


@router.get("/", response_model=list[HistoricalOfferRead])
def list_offers(
    ctx: CompanyContextDep,
    job_type: Optional[str] = None,
    building_type: Optional[str] = None,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    extraction_status: Optional[ExtractionStatus] = None,
    active_only: bool = True,
) -> list[HistoricalOfferRead]:
    session = ctx.session
    stmt = select(HistoricalOffer)
    if active_only:
        stmt = stmt.where(HistoricalOffer.active == True)  # noqa: E712
    if job_type:
        stmt = stmt.where(HistoricalOffer.job_type == job_type)
    if building_type:
        stmt = stmt.where(HistoricalOffer.building_type == building_type)
    if year_min:
        stmt = stmt.where(HistoricalOffer.year >= year_min)
    if year_max:
        stmt = stmt.where(HistoricalOffer.year <= year_max)
    if extraction_status:
        stmt = stmt.where(HistoricalOffer.extraction_status == extraction_status)
    return [_to_read(o) for o in session.exec(stmt).all()]


@router.get("/{offer_id}", response_model=HistoricalOfferRead)
def get_offer(offer_id: str, ctx: CompanyContextDep) -> HistoricalOfferRead:
    session = ctx.session
    offer = session.get(HistoricalOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="HistoricalOffer not found")
    return _to_read(offer)


@router.patch("/{offer_id}", response_model=HistoricalOfferRead)
def update_offer(
    offer_id: str, data: HistoricalOfferUpdate, ctx: CompanyContextDep
) -> HistoricalOfferRead:
    session = ctx.session
    offer = session.get(HistoricalOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="HistoricalOffer not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(offer, field, value)
    offer.updated_at = datetime.utcnow()
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return _to_read(offer)


@router.post("/{offer_id}/approve", response_model=HistoricalOfferRead)
def approve_offer(offer_id: str, ctx: CompanyContextDep) -> HistoricalOfferRead:
    session = ctx.session
    offer = session.get(HistoricalOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="HistoricalOffer not found")
    if offer.extraction_status not in {
        ExtractionStatus.needs_review, ExtractionStatus.extracted
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot approve offer with status '{offer.extraction_status}'",
        )
    offer.extraction_status = ExtractionStatus.approved
    offer.updated_at = datetime.utcnow()
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return _to_read(offer)


@router.get("/jobs/", response_model=list[ImportJobRead])
def list_import_jobs(
    ctx: CompanyContextDep, active_only: bool = True
) -> list[ImportJobRead]:
    session = ctx.session
    stmt = select(HistoricalOfferImportJob)
    if active_only:
        stmt = stmt.where(HistoricalOfferImportJob.active == True)  # noqa: E712
    return [ImportJobRead.model_validate(j) for j in session.exec(stmt).all()]


@router.delete("/{offer_id}", status_code=204)
def delete_offer(offer_id: str, ctx: CompanyContextDep) -> None:
    session = ctx.session
    offer = session.get(HistoricalOffer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="HistoricalOffer not found")
    offer.active = False
    session.add(offer)
    session.commit()
