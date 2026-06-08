"""CreditorMatchingService — matches a raw creditor name to an existing Creditor.

Matching strategy (in order):
1. Exact normalised name match against Creditor.name
2. Normalised name match against CreditorAlias.alias
3. No match → creates a new Creditor stub with risk_level=low, source=derived
   and adds the raw name as an alias.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Session, func, select

from ...models.creditor import Creditor, CreditorAlias, CreditorRiskLevel


def _norm(s: str) -> str:
    return s.strip().lower()


def match_or_create(
    session: Session,
    company_id: str,
    raw_name: str,
) -> tuple[Creditor, bool]:
    """Return (creditor, created).

    created=True means a new stub was created.
    Does NOT commit — caller commits.
    """
    norm = _norm(raw_name)

    # 1. Exact name match
    existing = session.exec(
        select(Creditor).where(
            Creditor.company_id == company_id,
            func.lower(Creditor.name) == norm,
            Creditor.active == True,  # noqa: E712
        )
    ).first()
    if existing:
        return existing, False

    # 2. Alias match
    alias = session.exec(
        select(CreditorAlias).where(
            func.lower(CreditorAlias.alias) == norm,
        )
    ).first()
    if alias:
        creditor = session.get(Creditor, alias.creditor_id)
        if creditor and creditor.company_id == company_id and creditor.active:
            return creditor, False

    # 3. Create stub
    creditor = Creditor(
        company_id=company_id,
        name=raw_name.strip(),
        risk_level=CreditorRiskLevel.low,
    )
    session.add(creditor)
    session.flush()  # get creditor.id

    # Record the raw name as a derived alias
    alias_record = CreditorAlias(
        creditor_id=creditor.id,
        alias=norm,
        source="derived",
    )
    session.add(alias_record)
    return creditor, True
