from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database.facilities import DEFAULT_FACILITY
from app.database.models import Base

_engine = None
_SessionLocal = None

# Tables that existed before the multi-facility feature; a plain
# `create_all()` only creates missing tables, so existing deployments need
# this column added in place (no data loss, no table drop).
_FACILITY_MIGRATION_TABLES = ("parking_availability", "pricing", "working_hours", "reservations")


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.postgres_url, pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def _add_facility_columns(engine) -> None:
    with engine.begin() as conn:
        for table in _FACILITY_MIGRATION_TABLES:
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS facility "
                    f"VARCHAR(50) NOT NULL DEFAULT '{DEFAULT_FACILITY}'"
                )
            )


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _add_facility_columns(engine)


def get_session() -> Session:
    return get_session_factory()()
