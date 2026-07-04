"""Database engine, session factory, and TimescaleDB-aware bootstrap.

The readings table is designed as a TimescaleDB hypertable (SRS 3.3), but
this environment may not have the extension installed. We try to enable it
and convert `readings` to a hypertable; if that fails we silently fall back
to plain PostgreSQL, where the composite (site_id, ts) index added in the
model keeps range queries fast enough for a 5-site pilot.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

engine = create_engine(settings.resolved_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def try_enable_timescale() -> bool:
    """Attempt to turn readings into a hypertable. Returns True on success."""
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            conn.execute(
                text(
                    "SELECT create_hypertable('readings', 'ts', "
                    "if_not_exists => TRUE, migrate_data => TRUE)"
                )
            )
        return True
    except Exception:
        # Extension not available (e.g. Postgres.app). Plain table + index is fine.
        return False


def session_scope() -> Session:
    """Plain session for background tasks (simulator, timeout sweeper)."""
    return SessionLocal()
