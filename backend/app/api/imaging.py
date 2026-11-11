"""Imagerie thoracique (F-C1 à F-C5) : liste chronologique, scores par pathologie avec incertitude, Grad-CAM,
vue déclarée et commentaire du médecin. Les scores sont ceux d'un modèle de recherche : aucun diagnostic."""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_patient_for_doctor, require_doctor
from app.db.models import Document, DocumentType, Imaging, Patient, User
from app.db.session import get_db
from app.services import imaging as imaging_service
from app.services import storage
from app.services.audit import audit
from app.services.imaging import run_analysis

router = APIRouter(tags=["imaging"])


def _owned_doc(db: Session, document_id: uuid.UUID, user: User) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or db.get(Patient, doc.patient_id).doctor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document introuvable.")
    if doc.type != DocumentType.radiographie:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ce document n'est pas une radiographie.")
    return doc


def _out(doc: Document, im: Imaging | None) -> dict:
    return {"document_id": str(doc.id), "imaging_id": str(im.id) if im else None, "date": doc.exam_date,
            "name": doc.original_name, "analyzed": bool(im and im.scores), "scores": im.scores if im else None,
            "uncertainty": im.uncertainty if im else None,
            "quality_flags": [f for f in (im.quality_flag or "").split(",") if f] if im else [],
            "view": im.view if im else None, "model_name": im.model_name if im else None,
            "model_version": im.model_version if im else None,
            "doctor_assessment": im.doctor_assessment if im else None}


@router.get("/patients/{patient_id}/imaging")
def list_imaging(patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> dict:
    docs = db.scalars(select(Document).where(Document.patient_id == patient.id,
                                             Document.type == DocumentType.radiographie)
                      .order_by(Document.exam_date.nulls_last(), Document.created_at))
    by_doc = {i.document_id: i for i in db.scalars(select(Imaging).join(Document).where(Document.patient_id == patient.id))}
    return {"pathologies": imaging_service.SHOWN, "model_name": imaging_service.MODEL_NAME,
            "items": [_out(d, by_doc.get(d.id)) for d in docs]}


@router.post("/documents/{document_id}/imaging")
def analyze_document(document_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> dict:
    doc = _owned_doc(db, document_id, user)
    im = run_analysis(db, doc)
    db.commit()
    audit(db, user.id, "imaging_analyze", "document", doc.id, {"model": im.model_name})
    return _out(doc, im)


@router.get("/documents/{document_id}/gradcam")
def gradcam(document_id: uuid.UUID, pathology: str = Query(...), user: User = Depends(require_doctor),
            db: Session = Depends(get_db)) -> Response:
    """Carte Grad-CAM (PNG transparent, taille de l'image d'origine), mise en cache sur le volume."""
    doc = _owned_doc(db, document_id, user)
    if pathology not in imaging_service.SHOWN:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Pathologie non prise en charge.")
    cache = storage.absolute(doc.file_path).with_name(f"{doc.id}.cam.{pathology.replace(' ', '_')}.png")
    if not cache.exists():
        cache.write_bytes(imaging_service.gradcam_overlay(storage.absolute(doc.file_path), pathology))
    audit(db, user.id, "imaging_gradcam", "document", doc.id, {"pathology": pathology})
    return Response(cache.read_bytes(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


class ImagingUpdate(BaseModel):
    view: Literal["face", "profil"] | None = None
    doctor_assessment: str | None = Field(default=None, max_length=2000)


@router.patch("/documents/{document_id}/imaging")
def update_imaging(document_id: uuid.UUID, body: ImagingUpdate, user: User = Depends(require_doctor),
                   db: Session = Depends(get_db)) -> dict:
    """Le médecin déclare la vue (une vue de profil est exclue des comparaisons) et note sa propre lecture."""
    doc = _owned_doc(db, document_id, user)
    im = db.scalar(select(Imaging).where(Imaging.document_id == doc.id))
    if im is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Radiographie non encore analysée.")
    if body.view is not None:
        im.view = body.view
    if body.doctor_assessment is not None:
        im.doctor_assessment = body.doctor_assessment.strip() or None
    db.commit()
    audit(db, user.id, "imaging_update", "document", doc.id, body.model_dump(exclude_none=True))
    return _out(doc, im)
