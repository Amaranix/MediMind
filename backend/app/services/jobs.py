"""Tâches asynchrones simples (F-03) : BackgroundTasks FastAPI + table `jobs` (pas de Celery ni Redis).

Chaque type de tâche s'enregistre avec @register("type"). Une tâche en échec garde son erreur et peut être
relancée. Au redémarrage, les tâches restées « running » sont remises en échec pour être rejouées.
"""
from __future__ import annotations

import logging
import traceback
import uuid
from collections.abc import Callable

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus, utcnow
from app.db.session import SessionLocal

log = logging.getLogger("medimind.jobs")
Handler = Callable[[Session, Job], None]
_HANDLERS: dict[str, Handler] = {}


def register(job_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        _HANDLERS[job_type] = fn
        return fn
    return deco


def create_job(db: Session, job_type: str, ref_id: str | uuid.UUID | None, user_id: uuid.UUID | None) -> Job:
    if job_type not in _HANDLERS:
        raise ValueError(f"type de tâche inconnu : {job_type}")
    job = Job(type=job_type, ref_id=str(ref_id) if ref_id else None, created_by=user_id)
    db.add(job)
    db.commit()
    return job


def run_job(job_id: uuid.UUID) -> None:
    """Exécute la tâche dans sa propre session (appelée par BackgroundTasks)."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None or job.status == JobStatus.running:
            return
        job.status, job.error, job.attempts = JobStatus.running, None, job.attempts + 1
        db.commit()
        try:
            _HANDLERS[job.type](db, job)
            job.status = JobStatus.done
        except Exception as exc:  # noqa: BLE001 - toute erreur est consignée dans le job
            db.rollback()
            job = db.get(Job, job_id)
            job.status = JobStatus.failed
            job.error = f"{type(exc).__name__}: {exc}"
            log.error("job failed", extra={"job_id": str(job_id)}, exc_info=True)
            log.debug(traceback.format_exc())
        job.finished_at = utcnow()
        db.commit()
    finally:
        db.close()


def reset_interrupted(db: Session) -> int:
    res = db.execute(update(Job).where(Job.status == JobStatus.running)
                     .values(status=JobStatus.failed, error="Interrompu par un redémarrage du serveur"))
    db.commit()
    return res.rowcount or 0


@register("noop")
def _noop(db: Session, job: Job) -> None:
    """Tâche de diagnostic (vérifie la chaîne asynchrone)."""
