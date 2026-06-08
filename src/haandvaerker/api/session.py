"""Session management endpoints.

POST   /session/select-company  — validate company, set signed cookie, return 200
GET    /session/current         — decode cookie, return {company_id, company_name}
DELETE /session/logout          — clear cookie, return 200
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from itsdangerous import URLSafeSerializer
from pydantic import BaseModel
from sqlmodel import Session

from ..config import settings
from ..database import get_session
from ..dependencies import COOKIE_NAME, CompanyContext, get_company_context
from ..models.company import Company

router = APIRouter(prefix="/session", tags=["session"])

SessionDep = Annotated[Session, Depends(get_session)]


class SelectCompanyRequest(BaseModel):
    company_id: str


class SelectCompanyResponse(BaseModel):
    company_id: str
    company_name: str


class CurrentSessionResponse(BaseModel):
    company_id: str
    company_name: str


# ── POST /session/select-company ──────────────────────────────────────────────

@router.post("/select-company", response_model=SelectCompanyResponse)
def select_company(
    data: SelectCompanyRequest,
    response: Response,
    session: SessionDep,
) -> SelectCompanyResponse:
    """Validate company exists and is active, then set a signed session cookie."""
    company = session.get(Company, data.company_id)
    if not company:
        raise HTTPException(
            status_code=422,
            detail=f"Virksomhed '{data.company_id}' ikke fundet.",
        )
    if not company.active:
        raise HTTPException(
            status_code=422,
            detail=f"Virksomhed '{data.company_id}' er inaktiv.",
        )
    s = URLSafeSerializer(settings.secret_key, salt="company-session")
    signed = s.dumps(data.company_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=signed,
        httponly=True,
        samesite="lax",
    )
    return SelectCompanyResponse(
        company_id=company.id,
        company_name=company.name,
    )


# ── GET /session/current ──────────────────────────────────────────────────────

@router.get("/current", response_model=CurrentSessionResponse)
def get_current(
    ctx: Annotated[CompanyContext, Depends(get_company_context)],
) -> CurrentSessionResponse:
    """Return the active company from the signed session cookie."""
    company = ctx.session.get(Company, ctx.company_id)
    if not company:
        raise HTTPException(
            status_code=401,
            detail=f"Virksomhed '{ctx.company_id}' ikke fundet.",
        )
    return CurrentSessionResponse(
        company_id=company.id,
        company_name=company.name,
    )


# ── DELETE /session/logout ────────────────────────────────────────────────────

@router.delete("/logout")
def logout(response: Response) -> dict:
    """Clear the session cookie."""
    response.delete_cookie(key=COOKIE_NAME)
    return {"detail": "Logget ud."}
