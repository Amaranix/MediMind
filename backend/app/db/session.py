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
        # Autant de connexions que de fils d'exécution de FastAPI (40) : sinon, sous charge (tâches OCR en fond +
        # requêtes de l'interface), des requêtes gardent une connexion en attendant un fil pendant que tous les fils
        # attendent une connexion (blocage observé au test de bout en bout, 15 connexions « idle in transaction »).
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=10, max_overflow=30,
                                pool_timeout=15)
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
