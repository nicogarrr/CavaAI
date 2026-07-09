from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy import inspect, text

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Lightweight forward-compat for SQLite/dev DBs created before new columns.
    try:
        inspector = inspect(engine)
        if "thesis_versions" in inspector.get_table_names():
            columns = {col["name"] for col in inspector.get_columns("thesis_versions")}
            if "input_fingerprint" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text("ALTER TABLE thesis_versions ADD COLUMN input_fingerprint VARCHAR(64)")
                    )
    except Exception:  # noqa: BLE001 — never block startup on optional alter
        pass

