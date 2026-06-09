from __future__ import annotations

import pathlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session

from ..database import get_session
from ..dependencies import CompanyContextDep
from ..models.company import Company

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_SIZE_BYTES = 2 * 1024 * 1024

LOGOS_DIR = pathlib.Path(__file__).parent.parent / "static" / "uploads" / "logos"

router = APIRouter(prefix="/companies", tags=["company-logo"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/logo", status_code=201)
async def upload_logo(
    file: UploadFile,
    ctx: CompanyContextDep,
    session: SessionDep,
) -> dict:
    suffix = pathlib.Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"File type '{suffix}' not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    data = await file.read(MAX_SIZE_BYTES + 1)
    if len(data) > MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"File exceeds maximum size of {MAX_SIZE_BYTES} bytes.",
        )

    company = session.get(Company, ctx.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    dest = LOGOS_DIR / f"{ctx.company_id}{suffix}"
    dest.write_bytes(data)

    logo_ref = f"/static/uploads/logos/{ctx.company_id}{suffix}"
    company.logo_ref = logo_ref
    session.add(company)
    session.commit()

    return {"logo_url": logo_ref}


@router.delete("/logo", status_code=204)
def delete_logo(
    ctx: CompanyContextDep,
    session: SessionDep,
) -> None:
    company = session.get(Company, ctx.company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    if company.logo_ref:
        for ext in ALLOWED_EXTENSIONS:
            candidate = LOGOS_DIR / f"{ctx.company_id}{ext}"
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass

    company.logo_ref = None
    session.add(company)
    session.commit()
