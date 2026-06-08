from collections.abc import Generator
from sqlmodel import SQLModel, Session, create_engine
from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    # D1=B — no Alembic; rely on reset_demo.bat dropping haandvaerker.db before
    # any schema-change test cycle. create_all() is a no-op for new columns on
    # existing tables. Pay-down: next schema change touching production-shaped
    # data must bootstrap Alembic first.
    # NOTE: for local demo reset, drop haandvaerker.db and rerun — see reset_demo.bat.
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
