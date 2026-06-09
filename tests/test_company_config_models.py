from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool


@pytest.fixture(name="mem_engine")
def mem_engine_fixture():
    from haandvaerker.models import company_config as _cc  # noqa: F401
    from haandvaerker.models.company import Company  # noqa: F401

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine


def test_all_three_tables_created(mem_engine):
    names = sa_inspect(mem_engine).get_table_names()
    assert "companyemailconfig" in names
    assert "companyaiconfig" in names
    assert "companypromptconfig" in names


def test_email_config_roundtrip(mem_engine):
    from haandvaerker.models.company import Company
    from haandvaerker.models.company_config import CompanyEmailConfig

    with Session(mem_engine) as session:
        company = Company(id="c-email-1", name="E-firma")
        session.add(company)
        session.commit()

        cfg = CompanyEmailConfig(
            company_id="c-email-1",
            imap_host="imap.example.com",
            imap_port=993,
            imap_user="user@example.com",
            imap_password="secret",  # noqa: S106
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="user@example.com",
            smtp_password="smtpsecret",  # noqa: S106
            smtp_from="noreply@example.com",
            smtp_use_tls=True,
        )
        session.add(cfg)
        session.commit()
        session.refresh(cfg)

    with Session(mem_engine) as session:
        loaded = session.get(CompanyEmailConfig, "c-email-1")
        assert loaded is not None
        assert loaded.imap_host == "imap.example.com"
        assert loaded.smtp_port == 587
        assert loaded.smtp_use_tls is True
        assert loaded.imap_password == "secret"  # noqa: S105


def test_email_config_defaults(mem_engine):
    from haandvaerker.models.company import Company
    from haandvaerker.models.company_config import CompanyEmailConfig

    with Session(mem_engine) as session:
        company = Company(id="c-email-2", name="E-firma-2")
        session.add(company)
        session.commit()

        cfg = CompanyEmailConfig(company_id="c-email-2")
        session.add(cfg)
        session.commit()
        session.refresh(cfg)

        assert cfg.imap_port == 993
        assert cfg.smtp_port == 587
        assert cfg.smtp_use_tls is True
        assert cfg.imap_host is None
        assert isinstance(cfg.updated_at, datetime)


def test_ai_config_roundtrip(mem_engine):
    from haandvaerker.models.company import Company
    from haandvaerker.models.company_config import CompanyAiConfig

    with Session(mem_engine) as session:
        company = Company(id="c-ai-1", name="AI-firma")
        session.add(company)
        session.commit()

        cfg = CompanyAiConfig(
            company_id="c-ai-1",
            endpoint="http://localhost:11434",
            model="llama3.1:8b",
            fallback_model="mistral:7b",
        )
        session.add(cfg)
        session.commit()
        session.refresh(cfg)

    with Session(mem_engine) as session:
        loaded = session.get(CompanyAiConfig, "c-ai-1")
        assert loaded is not None
        assert loaded.endpoint == "http://localhost:11434"
        assert loaded.model == "llama3.1:8b"
        assert loaded.fallback_model == "mistral:7b"
        assert isinstance(loaded.updated_at, datetime)


def test_prompt_config_roundtrip(mem_engine):
    from haandvaerker.models.company import Company
    from haandvaerker.models.company_config import CompanyPromptConfig

    with Session(mem_engine) as session:
        company = Company(id="c-prompt-1", name="Prompt-firma")
        session.add(company)
        session.commit()

        cfg = CompanyPromptConfig(
            company_id="c-prompt-1",
            draft_system="You are a helpful assistant.",
            draft_user="Context: {context}. Write a draft.",
        )
        session.add(cfg)
        session.commit()
        session.refresh(cfg)

    with Session(mem_engine) as session:
        loaded = session.get(CompanyPromptConfig, "c-prompt-1")
        assert loaded is not None
        assert loaded.draft_system == "You are a helpful assistant."
        assert "{context}" in loaded.draft_user
        assert isinstance(loaded.updated_at, datetime)


def test_email_config_read_password_set_flag():
    from haandvaerker.models.company_config import CompanyEmailConfig, CompanyEmailConfigRead

    cfg = CompanyEmailConfig(
        company_id="c1",
        imap_password="secret",  # noqa: S106
        smtp_password=None,
        updated_at=datetime(2024, 1, 1),
    )
    read = CompanyEmailConfigRead(
        company_id=cfg.company_id,
        imap_host=cfg.imap_host,
        imap_port=cfg.imap_port,
        imap_user=cfg.imap_user,
        imap_password_set=bool(cfg.imap_password),
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        smtp_user=cfg.smtp_user,
        smtp_password_set=bool(cfg.smtp_password),
        smtp_from=cfg.smtp_from,
        smtp_use_tls=cfg.smtp_use_tls,
        updated_at=cfg.updated_at,
    )
    assert read.imap_password_set is True
    assert read.smtp_password_set is False
    assert not hasattr(read, "imap_password")
    assert not hasattr(read, "smtp_password")


def test_email_config_update_all_optional():
    from haandvaerker.models.company_config import CompanyEmailConfigUpdate

    upd = CompanyEmailConfigUpdate()
    assert upd.imap_host is None
    assert upd.smtp_port is None


def test_ai_config_read_schema():
    from haandvaerker.models.company_config import CompanyAiConfigRead

    read = CompanyAiConfigRead(
        company_id="c1",
        endpoint="http://localhost:11434",
        model="llama3.1:8b",
        fallback_model=None,
        updated_at=datetime(2024, 1, 1),
    )
    assert read.model == "llama3.1:8b"
    assert read.fallback_model is None


def test_prompt_config_read_schema():
    from haandvaerker.models.company_config import CompanyPromptConfigRead

    read = CompanyPromptConfigRead(
        company_id="c1",
        draft_system="sys",
        draft_user="user {context}",
        updated_at=datetime(2024, 1, 1),
    )
    assert read.draft_system == "sys"
