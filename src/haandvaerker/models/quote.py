from __future__ import annotations
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional
from sqlmodel import Field, SQLModel


class QuoteStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    rejected = "rejected"


class QuoteUnit(str, Enum):
    m2 = "m2"
    stk = "stk"
    time = "time"
    lm = "lm"
    liter = "l"
    km = "km"


VAT_RATE = Decimal("0.25")


# ── Sequence table ──────────────────────────────────────────────────────────

class QuoteSequence(SQLModel, table=True):
    year: int = Field(primary_key=True)
    last_number: int = Field(default=0)


# ── Line item ────────────────────────────────────────────────────────────────

class QuoteLineCreate(SQLModel):
    description: str = Field(min_length=1, max_length=500)
    unit: QuoteUnit
    quantity: float = Field(gt=0)
    unit_price: float = Field(ge=0)


class QuoteLine(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    quote_id: str = Field(foreign_key="quote.id")
    description: str
    unit: QuoteUnit
    quantity: float
    unit_price: float
    line_total: float


class QuoteLineRead(SQLModel):
    id: str
    description: str
    unit: QuoteUnit
    quantity: float
    unit_price: float
    line_total: float


# ── Room measurement ─────────────────────────────────────────────────────────

class QuoteRoomCreate(SQLModel):
    name: str = Field(min_length=1, max_length=200)
    length_m: float
    width_m: float
    height_m: float
    window_m2: float = 0.0
    door_m2: float = 0.0
    price_per_m2: Optional[float] = None  # required for area quotes; validated at the API layer


class QuoteRoom(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    quote_id: str = Field(foreign_key="quote.id")
    name: str
    length_m: float
    width_m: float
    height_m: float
    window_m2: float = Field(default=0.0)
    door_m2: float = Field(default=0.0)
    price_per_m2: Optional[float] = Field(default=None)


class QuoteRoomRead(SQLModel):
    id: str
    name: str
    length_m: float
    width_m: float
    height_m: float
    window_m2: float
    door_m2: float
    price_per_m2: Optional[float]
    wall_m2: float
    ceiling_m2: float
    floor_m2: float
    wall_m2_net: float


# ── Quote header ─────────────────────────────────────────────────────────────

class QuoteCreate(SQLModel):
    id: Optional[str] = None
    project_id: str
    quote_type: str  # required — no default. Values: 'line' | 'area'
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    rooms: list[QuoteRoomCreate] = []
    lines: list[QuoteLineCreate] = []


class Quote(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    company_id: str = Field(foreign_key="company.id")
    quote_number: str = Field(index=True, sa_column_kwargs={"unique": True})
    title: str
    description: Optional[str] = None
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    status: QuoteStatus = Field(default=QuoteStatus.draft)
    quote_type: str = Field(default="line", max_length=20)
    # Values: 'line' | 'area'. Enforced at create/update in Phase 4.
    subtotal: float
    vat_amount: float
    total: float
    invoice_id: Optional[str] = Field(default=None)
    accept_token: Optional[str] = Field(
        default=None, index=True, sa_column_kwargs={"unique": True}
    )
    accepted_at: Optional[datetime] = Field(default=None)
    rejected_at: Optional[datetime] = Field(default=None)
    rejection_reason: Optional[str] = Field(default=None, max_length=500)
    active: bool = Field(default=True)


class QuoteRead(SQLModel):
    id: str
    company_id: str
    project_id: str
    quote_number: str
    title: str
    description: Optional[str]
    valid_until: Optional[date]
    notes: Optional[str]
    status: QuoteStatus
    quote_type: str = "line"
    subtotal: float
    vat_amount: float
    total: float
    invoice_id: Optional[str]
    accept_token: Optional[str]
    accepted_at: Optional[datetime]
    rejected_at: Optional[datetime]
    rejection_reason: Optional[str]
    active: bool
    rooms: list[QuoteRoomRead] = []
    lines: list[QuoteLineRead] = []


class QuotePublicRead(SQLModel):
    """Safe for public (customer-facing) — no internal IDs."""
    quote_number: str
    title: str
    description: Optional[str]
    valid_until: Optional[date]
    notes: Optional[str]
    status: QuoteStatus
    subtotal: float
    vat_amount: float
    total: float
    accepted_at: Optional[datetime]
    rejected_at: Optional[datetime]
    rejection_reason: Optional[str]
    company_name: str
    lines: list[QuoteLineRead] = []


class QuoteRejectBody(SQLModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class QuoteUpdate(SQLModel):
    quote_type: Optional[str] = None  # if provided, type change is validated and incompatible collection cleared
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    rooms: Optional[list[QuoteRoomCreate]] = None
    lines: Optional[list[QuoteLineCreate]] = None


# ── Calculation helpers ───────────────────────────────────────────────────────

def compute_room_m2(room: QuoteRoom) -> dict:
    length = Decimal(str(room.length_m))
    width = Decimal(str(room.width_m))
    height = Decimal(str(room.height_m))
    window = Decimal(str(room.window_m2))
    door = Decimal(str(room.door_m2))

    wall = 2 * (length + width) * height
    ceiling = length * width
    wall_net = max(Decimal("0"), wall - window - door)

    q = Decimal("0.01")
    return {
        "wall_m2": float(wall.quantize(q, ROUND_HALF_UP)),
        "ceiling_m2": float(ceiling.quantize(q, ROUND_HALF_UP)),
        "floor_m2": float(ceiling.quantize(q, ROUND_HALF_UP)),
        "wall_m2_net": float(wall_net.quantize(q, ROUND_HALF_UP)),
    }


def compute_line_total(quantity: float, unit_price: float) -> float:
    result = Decimal(str(quantity)) * Decimal(str(unit_price))
    return float(result.quantize(Decimal("0.01"), ROUND_HALF_UP))


def compute_quote_totals(line_totals: list[float]) -> tuple[float, float, float]:
    subtotal = sum(Decimal(str(t)) for t in line_totals)
    vat = (subtotal * VAT_RATE).quantize(Decimal("0.01"), ROUND_HALF_UP)
    total = subtotal + vat
    return float(subtotal), float(vat), float(total)
