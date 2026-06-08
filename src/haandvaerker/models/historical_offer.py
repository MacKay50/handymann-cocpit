from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class ExtractionStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    extracted = "extracted"
    needs_review = "needs_review"
    approved = "approved"
    failed = "failed"


class ImportJobStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    needs_review = "needs_review"
    completed = "completed"
    failed = "failed"


class ChunkType(str, Enum):
    extracted_text = "extracted_text"
    description = "description"
    price = "price"
    terms = "terms"
    notes = "notes"
    assumptions = "assumptions"
    exclusions = "exclusions"


class HistoricalOffer(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    company_id: Optional[str] = Field(default=None, foreign_key="company.id", index=True)
    source_file_path: str = Field(max_length=1000)
    source_file_hash: str = Field(max_length=64, index=True)
    title: Optional[str] = Field(default=None, max_length=500)
    address: Optional[str] = Field(default=None, max_length=500)
    offer_number: Optional[str] = Field(default=None, max_length=100)
    year: Optional[int] = Field(default=None)
    customer_type: Optional[str] = Field(default=None, max_length=100)
    job_type: Optional[str] = Field(default=None, max_length=100)
    building_type: Optional[str] = Field(default=None, max_length=100)
    room_type: Optional[str] = Field(default=None, max_length=100)
    area_m2: Optional[float] = Field(default=None)
    wall_area_m2: Optional[float] = Field(default=None)
    ceiling_area_m2: Optional[float] = Field(default=None)
    floor_area_m2: Optional[float] = Field(default=None)
    door_count: Optional[int] = Field(default=None)
    window_count: Optional[int] = Field(default=None)
    surface_condition: Optional[str] = Field(default=None, max_length=200)
    preparation_work: Optional[str] = Field(default=None)
    treatment: Optional[str] = Field(default=None)
    materials: Optional[str] = Field(default=None)
    access_conditions: Optional[str] = Field(default=None)
    special_conditions: Optional[str] = Field(default=None)
    price_ex_vat: Optional[float] = Field(default=None)
    vat: Optional[float] = Field(default=None)
    price_inc_vat: Optional[float] = Field(default=None)
    estimated_hours: Optional[float] = Field(default=None)
    actual_hours: Optional[float] = Field(default=None)
    accepted_status: Optional[str] = Field(default=None, max_length=50)
    summary: Optional[str] = Field(default=None)
    assumptions: Optional[str] = Field(default=None)
    exclusions: Optional[str] = Field(default=None)
    extraction_status: ExtractionStatus = Field(default=ExtractionStatus.needs_review)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HistoricalOfferChunk(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    historical_offer_id: str = Field(foreign_key="historicaloffer.id", index=True)
    chunk_text: str
    chunk_type: ChunkType = Field(default=ChunkType.extracted_text)
    page_number: Optional[int] = Field(default=None)
    embedding_json: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HistoricalOfferImportJob(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    file_path: str = Field(max_length=1000)
    file_hash: str = Field(max_length=64, index=True)
    status: ImportJobStatus = Field(default=ImportJobStatus.pending)
    extracted_text: Optional[str] = Field(default=None)
    extracted_json: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None, max_length=1000)
    historical_offer_id: Optional[str] = Field(default=None)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HistoricalComparisonReport(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    quote_preparation_id: Optional[str] = Field(default=None)
    query_summary: Optional[str] = Field(default=None, max_length=500)
    matched_offer_ids_json: str = Field(default="[]")
    price_range_low: Optional[float] = Field(default=None)
    price_range_median: Optional[float] = Field(default=None)
    price_range_high: Optional[float] = Field(default=None)
    price_per_m2_low: Optional[float] = Field(default=None)
    price_per_m2_median: Optional[float] = Field(default=None)
    price_per_m2_high: Optional[float] = Field(default=None)
    suggested_questions_json: Optional[str] = Field(default=None)
    relevant_assumptions: Optional[str] = Field(default=None)
    relevant_exclusions: Optional[str] = Field(default=None)
    comparison_summary: Optional[str] = Field(default=None)
    active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Read / Create / Update schemas ──────────────────────────────────────────

class HistoricalOfferRead(SQLModel):
    id: str
    source_file_path: str
    source_file_hash: str
    title: Optional[str]
    address: Optional[str]
    offer_number: Optional[str]
    year: Optional[int]
    customer_type: Optional[str]
    job_type: Optional[str]
    building_type: Optional[str]
    room_type: Optional[str]
    area_m2: Optional[float]
    wall_area_m2: Optional[float]
    ceiling_area_m2: Optional[float]
    floor_area_m2: Optional[float]
    door_count: Optional[int]
    window_count: Optional[int]
    surface_condition: Optional[str]
    preparation_work: Optional[str]
    treatment: Optional[str]
    materials: Optional[str]
    access_conditions: Optional[str]
    special_conditions: Optional[str]
    price_ex_vat: Optional[float]
    vat: Optional[float]
    price_inc_vat: Optional[float]
    estimated_hours: Optional[float]
    actual_hours: Optional[float]
    accepted_status: Optional[str]
    summary: Optional[str]
    assumptions: Optional[str]
    exclusions: Optional[str]
    extraction_status: ExtractionStatus
    active: bool
    created_at: datetime
    updated_at: datetime
    price_per_m2: Optional[float] = None


class HistoricalOfferUpdate(SQLModel):
    title: Optional[str] = Field(default=None, max_length=500)
    address: Optional[str] = None
    offer_number: Optional[str] = None
    year: Optional[int] = None
    customer_type: Optional[str] = None
    job_type: Optional[str] = None
    building_type: Optional[str] = None
    room_type: Optional[str] = None
    area_m2: Optional[float] = None
    wall_area_m2: Optional[float] = None
    ceiling_area_m2: Optional[float] = None
    floor_area_m2: Optional[float] = None
    door_count: Optional[int] = None
    window_count: Optional[int] = None
    surface_condition: Optional[str] = None
    preparation_work: Optional[str] = None
    treatment: Optional[str] = None
    materials: Optional[str] = None
    access_conditions: Optional[str] = None
    special_conditions: Optional[str] = None
    price_ex_vat: Optional[float] = None
    vat: Optional[float] = None
    price_inc_vat: Optional[float] = None
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    accepted_status: Optional[str] = None
    summary: Optional[str] = None
    assumptions: Optional[str] = None
    exclusions: Optional[str] = None


class ImportJobRead(SQLModel):
    id: str
    file_path: str
    file_hash: str
    status: ImportJobStatus
    extracted_text: Optional[str]
    extracted_json: Optional[str]
    error_message: Optional[str]
    historical_offer_id: Optional[str]
    active: bool
    created_at: datetime
    updated_at: datetime


class ComparisonReportRead(SQLModel):
    id: str
    quote_preparation_id: Optional[str]
    query_summary: Optional[str]
    matched_offer_ids: list[str] = []
    price_range_low: Optional[float]
    price_range_median: Optional[float]
    price_range_high: Optional[float]
    price_per_m2_low: Optional[float]
    price_per_m2_median: Optional[float]
    price_per_m2_high: Optional[float]
    suggested_questions: list[str] = []
    relevant_assumptions: Optional[str]
    relevant_exclusions: Optional[str]
    comparison_summary: Optional[str]
    matched_offers: list[HistoricalOfferRead] = []
    active: bool
    created_at: datetime
