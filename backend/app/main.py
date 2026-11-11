"""Point d'entrée FastAPI. Toutes les routes sont préfixées par /api (le proxy Caddy sert le frontend sur /)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api import auth, documents, patients, system, users
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.security import hash_password
from app.db.models import Role, User
from app.db.session import SessionLocal, get_engine
from app.services.jobs import reset_interrupted
from app.services.referential import get_referential, sync_parameters

log = logging.getLogger("medimind")


def bootstrap() -> None:
    """Synchronise le référentiel, crée l'administrateur initial et remet en échec les tâches interrompues."""
    s = get_settings()
    get_engine()
    ref = get_referential()  # lève une erreur si le YAML est invalide : l'application ne démarre pas
    with SessionLocal() as db:
        sync_parameters(db, ref)
        if s.admin_email and s.admin_password and not db.scalar(select(User).where(User.role == Role.admin)):
            db.add(User(name="Administrateur", email=s.admin_email.lower(),
                        password_hash=hash_password(s.admin_password), role=Role.admin))
            db.commit()
            log.info("administrateur initial créé")
        n = reset_interrupted(db)
        if n:
            log.warning(f"{n} tâche(s) interrompue(s) remise(s) en échec")
    s.storage_path.mkdir(parents=True, exist_ok=True)
    log.info(f"référentiel clinique v{ref.version} chargé ({len(ref.parameters)} paramètres, "
             f"{len(ref.alert_rules)} règles)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    bootstrap()
    yield


def create_app(run_bootstrap: bool = True) -> FastAPI:
    app = FastAPI(title="MediMind API", version="0.1.0", lifespan=lifespan if run_bootstrap else None,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    for r in (auth.router, users.router, patients.router, documents.router, system.router):
        app.include_router(r, prefix="/api")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"].removeprefix("Value error, ")}
                  for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": "Données invalides.", "errors": errors})

    return app


app = create_app()
