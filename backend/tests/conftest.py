"""Fixtures : base SQLite en mémoire (types JSON génériques), application sans démarrage réseau."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-0123456789")
os.environ["COOKIE_SECURE"] = "false"           # le client de test parle en http
os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"  # port fermé : Ollama « injoignable » sans attente
os.environ["LLM_ENABLED"] = "false"              # le repli LLM n'est jamais appelé pendant les tests
os.environ["ASSISTANT_SEARCH"] = "false"         # pas de modèle de recherche pendant les tests
os.environ["IMAGING_PRELOAD"] = "false"          # le modèle d'imagerie n'est pas préchargé pendant les tests
os.environ["STORAGE_PATH"] = tempfile.mkdtemp(prefix="medimind-test-")
_WIN_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"   # poste de développement Windows
if "TESSERACT_CMD" not in os.environ and os.path.exists(_WIN_TESSERACT):
    os.environ["TESSERACT_CMD"] = _WIN_TESSERACT

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.models import Base, Role, User
from app.db.session import SessionLocal, set_engine
from app.main import create_app
from app.services.referential import get_referential, sync_parameters

PASSWORD = "motdepasse-solide-42"


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    # SQLite n'applique les clés étrangères (et donc les cascades) qu'à la demande, comme PostgreSQL le fait toujours
    event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    set_engine(engine)
    with SessionLocal() as db:
        sync_parameters(db, get_referential())
    yield engine
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def client(db_engine):
    from app.core import ratelimit
    ratelimit.reset()  # compteur de tentatives partagé par le processus : repartir de zéro à chaque test
    return TestClient(create_app(run_bootstrap=False))


def make_user(db, email: str, role: Role = Role.doctor, active: bool = True) -> User:
    user = User(name=email.split("@")[0], email=email, password_hash=hash_password(PASSWORD), role=role,
                is_active=active)
    db.add(user)
    db.commit()
    return user


def login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


PATIENT = {"first_name": "Karim", "last_name": "Alaoui", "birth_date": "1962-03-14", "sex": "M", "height_cm": 172,
           "pack_years": 40}
