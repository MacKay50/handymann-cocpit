"""Test that PATCH /companies/{id} and DELETE /companies/{id}
require correct session company (CompanyContextDep ownership check)."""

import uuid
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from haandvaerker.models.company import Company


def test_patch_own_company_succeeds(client: TestClient, company_id: str) -> None:
    """PATCH with session company == target company → 200."""
    r = client.patch(f"/companies/{company_id}", json={"name": "Opdateret Navn"})
    assert r.status_code == 200
    assert r.json()["name"] == "Opdateret Navn"


def test_patch_other_company_forbidden(client: TestClient, session: Session) -> None:
    """PATCH with session for company A trying to edit company B → 403."""
    # Create a second company directly in the session (bypasses CompanyContextDep)
    other_company = Company(id=str(uuid.uuid4()), name="Anden Virksomhed")
    session.add(other_company)
    session.commit()

    r = client.patch(f"/companies/{other_company.id}", json={"name": "Hacket Navn"})
    assert r.status_code == 403
    assert r.json()["detail"] == "Adgang nægtet."


def test_delete_own_company_succeeds(client: TestClient, company_id: str) -> None:
    """DELETE with session company == target company → 204."""
    r = client.delete(f"/companies/{company_id}")
    assert r.status_code == 204


def test_delete_other_company_forbidden(client: TestClient, session: Session) -> None:
    """DELETE with session for company A trying to deactivate company B → 403."""
    other_company = Company(id=str(uuid.uuid4()), name="Anden Virksomhed 2")
    session.add(other_company)
    session.commit()

    r = client.delete(f"/companies/{other_company.id}")
    assert r.status_code == 403
    assert r.json()["detail"] == "Adgang nægtet."
