"""Moteur SQLAlchemy et fabrique de sessions."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True)
        SessionLocal.configure(bind=_engine)
    return _engine


def set_engine(engine: Engine) -> None:
    """Utilisé par les tests pour brancher une base temporaire."""
    global _engine
    _engine = engine
    SessionLocal.configure(bind=engine)


def get_db() -> Iterator[Session]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
