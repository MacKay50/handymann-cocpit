"""Shared FastAPI dependencies.

The single authorised source of ``company_id`` for all routers is
``get_company_context`` / ``CompanyContextDep``.  No router may accept
``company_id`` as a query-parameter or body field — it always comes from
the signed session cookie set by ``POST /session/select-company``.
Exception: the public ``/forespoergsel`` endpoint accepts ``company_id``
as a query-parameter (no session cookie — unauthenticated public form).

Iron Law 2: missing or invalid cookie → 401, never a silent default.
"""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, URLSafeSerializer
from sqlmodel import Session

from .config import settings
from .database import get_session
from .models.company import Company

# Cookie name used across session.py and this module.
COOKIE_NAME = "haandvaerker_company"


@dataclass
class CompanyContext:
    """Carries the validated session state into every handler."""
    session: Session
    company_id: str


def get_company_context(
    request: Request,
    session: Session = Depends(get_session),
) -> CompanyContext:
    """FastAPI dependency: decode the signed session cookie → CompanyContext.

    Raises:
        HTTPException 401: cookie absent, tampered, or refers to an inactive company.
    """
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        raise HTTPException(
            status_code=401,
            detail=(
                "Ingen aktiv virksomhedssession. "
                "Gå til forsiden og vælg virksomhed."
            ),
        )
    try:
        s = URLSafeSerializer(settings.secret_key, salt="company-session")
        company_id: str = s.loads(cookie)
    except BadSignature:
        raise HTTPException(
            status_code=401,
            detail="Ugyldig session-cookie. Vælg virksomhed igen.",
        )
    company = session.get(Company, company_id)
    if not company or not company.active:
        raise HTTPException(
            status_code=401,
            detail=f"Virksomhed '{company_id}' ikke fundet eller inaktiv.",
        )
    return CompanyContext(session=session, company_id=company_id)


CompanyContextDep = Annotated[CompanyContext, Depends(get_company_context)]
