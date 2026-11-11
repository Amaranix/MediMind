"""Santé du service, tâches, référentiel et journal d'audit."""
from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_admin
from app.core.config import get_settings
from app.db.models import AuditLog, Job, JobStatus, Role, User
from app.db.session import get_db
from app.schemas import AuditOut, HealthOut, JobOut
from app.services.jobs import run_job
from app.services.referential import get_referential

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)) -> HealthOut:
    s = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "indisponible"
    try:
        r = httpx.get(f"{s.ollama_url}/api/tags", timeout=2.0)
        names = {m.get("name") for m in r.json().get("models", [])}
        ollama = "ok" if s.ollama_model in names else f"modèle {s.ollama_model} absent"
    except Exception:  # noqa: BLE001
        ollama = "injoignable"
    return HealthOut(status="ok" if database == "ok" else "dégradé", database=database, ollama=ollama,
                     ollama_model=s.ollama_model, imaging_model="non chargé (phase 5)",
                     referential_version=get_referential().version)


@router.get("/referential")
def referential(user: User = Depends(current_user)) -> dict:
    return get_referential().model_dump()


def _own_job(job_id: uuid.UUID, user: User, db: Session) -> Job:
    job = db.get(Job, job_id)
    if job is None or (job.created_by != user.id and user.role != Role.admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tâche introuvable.")
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Job:
    return _own_job(job_id, user, db)


@router.post("/jobs/{job_id}/retry", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def retry_job(job_id: uuid.UUID, background: BackgroundTasks, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> Job:
    job = _own_job(job_id, user, db)
    if job.status != JobStatus.failed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Seule une tâche en échec peut être relancée.")
    job.status, job.error = JobStatus.queued, None
    db.commit()
    background.add_task(run_job, job.id)
    return job


@router.get("/audit", response_model=list[AuditOut])
def audit_log(admin: User = Depends(require_admin), db: Session = Depends(get_db),
              limit: int = Query(100, ge=1, le=1000)) -> list[AuditLog]:
    """Métadonnées d'accès uniquement (aucun contenu clinique)."""
    return list(db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)))
