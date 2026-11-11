"""Configuration de l'application (variables d'environnement, voir .env.example)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _default_referential() -> Path:
    # Conteneur : /app/referential ; développement local : <dépôt>/referential
    for candidate in (BACKEND_DIR / "referential", BACKEND_DIR.parent / "referential"):
        if candidate.exists():
            return candidate / "referentiel_clinique.yaml"
    return BACKEND_DIR / "referential" / "referentiel_clinique.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MediMind"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://medimind:medimind@localhost:5432/medimind"

    jwt_secret: str = Field(default="change-me-in-env", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    cookie_secure: bool = True

    admin_email: str | None = None
    admin_password: str | None = None

    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "llama3.2:3b"

    storage_path: Path = BACKEND_DIR / "storage"
    referential_path: Path = Field(default_factory=_default_referential)

    max_upload_mb: int = 25
    tesseract_cmd: str = "tesseract"
    llm_timeout_s: float = 60.0
    llm_enabled: bool = True
    imaging_preload: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
