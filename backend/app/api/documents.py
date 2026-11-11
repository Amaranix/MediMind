"""Dépôt de documents (F-A3), consultation et validation des valeurs extraites (F-A8)."""
from __future__ import annotations

import datetime as dt
import uuid

import pymupdf
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_patient_for_doctor, require_doctor
from app.core.config import get_settings
from app.db.models import (
    ClinicalEvent,
    Document,
    DocumentStatus,
    DocumentType,
    Job,
    Measurement,
    Patient,
    Treatment,
    User,
    ValidationStatus,
    utcnow,
)
from app.db.session import get_db
from app.schemas import (
    DocumentOut,
    DocumentUpdate,
    MeasurementAction,
    MeasurementOut,
    UploadResult,
)
from app.services import alerts as alert_engine
from app.services import storage
from app.services.audit import audit
from app.services.ingestion import job as ingestion_job  # noqa: F401 - enregistre la tâche ingest_document
from app.services.ingestion.job import refresh_document_status
from app.services.jobs import create_job, run_job
from app.services.referential import get_referential

router = APIRouter(tags=["documents"])
BULK_MIN_CONFIDENCE = 0.95
OPEN_STATUSES = (ValidationStatus.pending, ValidationStatus.suspect)


# ---------------------------------------------------------------- accès
def get_document_for_doctor(document_id: uuid.UUID, user: User = Depends(require_doctor),
                            db: Session = Depends(get_db)) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or db.get(Patient, doc.patient_id).doctor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document introuvable.")
    return doc


def get_measurement_for_doctor(measurement_id: uuid.UUID, user: User = Depends(require_doctor),
                               db: Session = Depends(get_db)) -> Measurement:
    m = db.get(Measurement, measurement_id)
    if m is None or db.get(Patient, m.patient_id).doctor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mesure introuvable.")
    return m


def _out(db: Session, doc: Document) -> DocumentOut:
    counts: dict = {}
    for model in (Measurement, Treatment, ClinicalEvent):
        for st, n in db.execute(select(model.validation_status, func.count()).where(model.source_document_id == doc.id)
                                .group_by(model.validation_status)).all():
            counts[st] = counts.get(st, 0) + n
    out = DocumentOut.model_validate(doc)
    out.type, out.status = doc.type.value, doc.status.value
    out.pending_count = sum(counts.get(s, 0) for s in OPEN_STATUSES)
    out.validated_count = counts.get(ValidationStatus.validated, 0) + counts.get(ValidationStatus.corrected, 0)
    return out


# ---------------------------------------------------------------- dépôt
@router.post("/patients/{patient_id}/documents", response_model=list[UploadResult],
             status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(background: BackgroundTasks, files: list[UploadFile] = File(...),
                           exam_date: dt.date | None = Form(None), doc_type: str | None = Form(None),
                           patient: Patient = Depends(get_patient_for_doctor), user: User = Depends(require_doctor),
                           db: Session = Depends(get_db)) -> list[UploadResult]:
    if doc_type and doc_type not in {t.value for t in DocumentType}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Type de document inconnu.")
    if exam_date and exam_date > dt.date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La date d'examen est dans le futur.")
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    results = []
    for f in files:
        name = (f.filename or "document")[:255]
        data = await f.read(max_bytes + 1)
        if len(data) > max_bytes:
            limit = get_settings().max_upload_mb
            results.append(UploadResult(filename=name, status="rejected",
                                        message=f"Fichier trop volumineux (maximum {limit} Mo)."))
            continue
        kind = storage.sniff(data)
        if kind is None:
            results.append(UploadResult(filename=name, status="rejected",
                                        message="Format non pris en charge : déposez un PDF, un JPG ou un PNG."))
            continue
        digest = storage.sha256(data)
        dup = db.scalar(select(Document).where(Document.patient_id == patient.id, Document.sha256 == digest))
        if dup:
            results.append(UploadResult(filename=name, status="duplicate", document_id=dup.id,
                                        message=f"Déjà déposé le {dup.created_at:%d/%m/%Y} ({dup.original_name})."))
            continue
        doc_id = uuid.uuid4()
        doc = Document(id=doc_id, patient_id=patient.id, original_name=name, mime_type=kind[0], sha256=digest,
                       file_path=storage.save(patient.id, doc_id, kind[1], data),
                       exam_date=exam_date, date_source="user" if exam_date else None,
                       type=DocumentType(doc_type) if doc_type else DocumentType.inconnu,
                       type_source="user" if doc_type else None)
        db.add(doc)
        db.commit()
        job = create_job(db, "ingest_document", doc.id, user.id)
        background.add_task(run_job, job.id)
        audit(db, user.id, "document_upload", "document", doc.id, {"patient_id": str(patient.id)})
        results.append(UploadResult(filename=name, status="queued", document_id=doc.id, job_id=job.id))
    return results


@router.get("/patients/{patient_id}/documents", response_model=list[DocumentOut])
def list_documents(patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> list:
    docs = db.scalars(select(Document).where(Document.patient_id == patient.id)
                      .order_by(Document.exam_date.desc().nulls_first(), Document.created_at.desc()))
    return [_out(db, d) for d in docs]


@router.get("/patients/{patient_id}/jobs/active")
def active_jobs(patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> dict:
    ids = [str(d) for d in db.scalars(select(Document.id).where(Document.patient_id == patient.id))]
    n = db.scalar(select(func.count()).select_from(Job).where(Job.ref_id.in_(ids),
                                                              Job.status.in_(["queued", "running"]))) if ids else 0
    return {"active": n}


# ---------------------------------------------------------------- document
@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(doc: Document = Depends(get_document_for_doctor), user: User = Depends(require_doctor),
                 db: Session = Depends(get_db)) -> DocumentOut:
    audit(db, user.id, "document_read", "document", doc.id)
    return _out(db, doc)


@router.patch("/documents/{document_id}", response_model=DocumentOut)
def update_document(body: DocumentUpdate, background: BackgroundTasks,
                    doc: Document = Depends(get_document_for_doctor), user: User = Depends(require_doctor),
                    db: Session = Depends(get_db)) -> DocumentOut:
    """Correction du type ou de la date par le médecin. Un changement de type relance l'extraction."""
    rerun = False
    if body.type is not None:
        if body.type not in {t.value for t in DocumentType}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Type de document inconnu.")
        rerun = body.type != doc.type.value
        doc.type, doc.type_source, doc.type_confidence = DocumentType(body.type), "user", 1.0
    if body.exam_date is not None:
        if body.exam_date > dt.date.today():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La date d'examen est dans le futur.")
        doc.exam_date, doc.date_source = body.exam_date, "user"
        for m in db.scalars(select(Measurement).where(Measurement.source_document_id == doc.id,
                                                      Measurement.validation_status.in_(OPEN_STATUSES))):
            m.date = body.exam_date
        doc.warnings = [w for w in (doc.warnings or []) if "Date d'examen introuvable" not in w]
        for t in db.scalars(select(Treatment).where(Treatment.source_document_id == doc.id,
                                                    Treatment.validation_status.in_(OPEN_STATUSES))):
            t.start_date = body.exam_date
            t.end_date = body.exam_date + dt.timedelta(days=t.duration_days) if t.duration_days else None
        alert_engine.recompute(db, get_referential(), doc.patient_id)
    db.commit()
    audit(db, user.id, "document_update", "document", doc.id, body.model_dump(exclude_none=True, mode="json"))
    if rerun:
        job = create_job(db, "ingest_document", doc.id, user.id)
        background.add_task(run_job, job.id)
    return _out(db, doc)


@router.get("/documents/{document_id}/file")
def document_file(doc: Document = Depends(get_document_for_doctor)) -> FileResponse:
    return FileResponse(storage.absolute(doc.file_path), media_type=doc.mime_type,
                        headers={"Cache-Control": "private, no-store"})


@router.get("/documents/{document_id}/pages/{page}")
def document_page(page: int, width: int = Query(1000, ge=300, le=2000),
                  doc: Document = Depends(get_document_for_doctor)) -> FileResponse:
    """Aperçu PNG d'une page (mis en cache), sur lequel le frontend superpose les boîtes normalisées."""
    cache = storage.page_cache(doc.file_path, page, width)
    if not cache.exists():
        src = storage.absolute(doc.file_path)
        if doc.mime_type == "application/pdf":
            with pymupdf.open(src) as pdf:
                if not 0 <= page < len(pdf):
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Page inexistante.")
                pg = pdf[page]
                pix = pg.get_pixmap(matrix=pymupdf.Matrix(width / pg.rect.width, width / pg.rect.width))
                pix.save(cache)
        else:
            if page != 0:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Page inexistante.")
            img = Image.open(src)
            img.thumbnail((width, width * 2))
            img.convert("RGB").save(cache)
    return FileResponse(cache, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------- mesures et validation
@router.get("/documents/{document_id}/measurements", response_model=list[MeasurementOut])
def document_measurements(doc: Document = Depends(get_document_for_doctor), db: Session = Depends(get_db)) -> list:
    order = {c.code: i for i, c in enumerate(get_referential().parameters)}
    rows = list(db.scalars(select(Measurement).where(Measurement.source_document_id == doc.id)))
    rows.sort(key=lambda m: ((m.bbox or {}).get("page", 0), (m.bbox or {}).get("y0", order.get(m.parameter_code, 0))))
    return [MeasurementOut.model_validate(m).model_copy(update={"validation_status": m.validation_status.value})
            for m in rows]


@router.patch("/measurements/{measurement_id}", response_model=MeasurementOut)
def act_on_measurement(body: MeasurementAction, m: Measurement = Depends(get_measurement_for_doctor),
                       user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> MeasurementOut:
    ref = get_referential()
    before = {"value": m.value, "status": m.validation_status.value, "context": m.context}
    if body.action == "correct":
        if body.value is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Indiquez la valeur corrigée.")
        lo, hi = ref.parameter(m.parameter_code).plausible
        if not lo <= body.value <= hi:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Valeur hors des bornes plausibles ({lo} à {hi} {m.unit}).")
        m.value = body.value
        if body.context is not None:
            unknown = set(body.context) - set(ref.contexts)
            if unknown:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Contexte inconnu : {sorted(unknown)}")
            m.context = sorted(body.context)
        m.validation_status = ValidationStatus.corrected
    elif body.action == "validate":
        m.validation_status = ValidationStatus.validated
    elif body.action == "reject":
        m.validation_status = ValidationStatus.rejected
    else:
        m.validation_status = ValidationStatus.pending
    m.validated_by = None if body.action == "reset" else user.id
    m.validated_at = None if body.action == "reset" else utcnow()
    if m.source_document_id:
        refresh_document_status(db, db.get(Document, m.source_document_id))
    alert_engine.recompute(db, ref, m.patient_id)
    db.commit()
    audit(db, user.id, f"measurement_{body.action}", "measurement", m.id,
          {"before": before, "after": {"value": m.value, "status": m.validation_status.value, "context": m.context}})
    return MeasurementOut.model_validate(m).model_copy(update={"validation_status": m.validation_status.value})


@router.post("/documents/{document_id}/validate-confident", response_model=DocumentOut)
def validate_confident(doc: Document = Depends(get_document_for_doctor), user: User = Depends(require_doctor),
                       db: Session = Depends(get_db)) -> DocumentOut:
    """Validation groupée des seules valeurs sûres : confiance >= 0,95 et aucun signalement. Les valeurs lues par
    OCR (confiance plafonnée à 0,9) restent toujours à valider une par une."""
    n = 0
    for m in db.scalars(select(Measurement).where(Measurement.source_document_id == doc.id,
                                                  Measurement.validation_status == ValidationStatus.pending)):
        if (m.confidence or 0) >= BULK_MIN_CONFIDENCE and not m.flags:
            m.validation_status, m.validated_by, m.validated_at = ValidationStatus.validated, user.id, utcnow()
            n += 1
    refresh_document_status(db, doc)
    alert_engine.recompute(db, get_referential(), doc.patient_id)
    db.commit()
    audit(db, user.id, "measurement_bulk_validate", "document", doc.id, {"count": n})
    return _out(db, doc)


@router.get("/patients/{patient_id}/pending-count")
def pending_count(patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> dict:
    n = sum(db.scalar(select(func.count()).select_from(model).where(
        model.patient_id == patient.id, model.validation_status.in_(OPEN_STATUSES)))
        for model in (Measurement, Treatment, ClinicalEvent))
    docs = db.scalar(select(func.count()).select_from(Document).where(
        Document.patient_id == patient.id, Document.status == DocumentStatus.extracted))
    return {"measurements": n, "documents": docs}
