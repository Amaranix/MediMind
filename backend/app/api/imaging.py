"""Imagerie thoracique (F-C1 à F-C7) : liste chronologique, scores par pathologie avec incertitude, Grad-CAM,
vue déclarée et commentaire du médecin, annotations (F-C7), qualification de l'évolution entre deux clichés par le
médecin (F-C6). Les scores sont ceux d'un modèle de recherche : aucun diagnostic, aucun verdict d'évolution."""
from __future__ import annotations

import io
import json
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_patient_for_doctor, require_doctor
from app.db.models import Document, DocumentType, Imaging, Patient, RadiographComparison, User, utcnow
from app.db.session import get_db
from app.services import imaging as imaging_service
from app.services import registration, storage
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
            "doctor_assessment": im.doctor_assessment if im else None,
            "annotations": (im.annotations or []) if im else []}


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


class Annotation(BaseModel):
    """Flèche (x1, y1 -> x2, y2) ou texte (x1, y1), coordonnées normalisées dans l'image (0 à 1)."""
    type: Literal["arrow", "text"]
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float | None = Field(default=None, ge=0, le=1)
    y2: float | None = Field(default=None, ge=0, le=1)
    text: str | None = Field(default=None, max_length=200)


class ImagingUpdate(BaseModel):
    view: Literal["face", "profil"] | None = None
    doctor_assessment: str | None = Field(default=None, max_length=2000)
    annotations: list[Annotation] | None = Field(default=None, max_length=50)


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
    if body.annotations is not None:
        bad = [a for a in body.annotations if (a.type == "arrow" and (a.x2 is None or a.y2 is None))
               or (a.type == "text" and not (a.text or "").strip())]
        if bad:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Annotation incomplète (flèche sans fin ou texte vide).")
        im.annotations = [a.model_dump(exclude_none=True) for a in body.annotations]
    db.commit()
    audit(db, user.id, "imaging_update", "document", doc.id, body.model_dump(exclude_none=True))
    return _out(doc, im)


# ---------------------------------------------------------------- F-C6 : qualification par le médecin


def _cmp_out(c: RadiographComparison) -> dict:
    return {"document_a_id": str(c.document_a_id), "document_b_id": str(c.document_b_id),
            "qualification": c.qualification, "comment": c.comment, "updated_at": c.updated_at}


@router.get("/patients/{patient_id}/radiograph-comparisons")
def list_comparisons(patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(RadiographComparison).where(RadiographComparison.patient_id == patient.id)
                      .order_by(RadiographComparison.updated_at.desc()))
    return [_cmp_out(c) for c in rows]


class ComparisonIn(BaseModel):
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    qualification: Literal["amelioration", "stable", "aggravation", "non_evaluable"]
    comment: str | None = Field(default=None, max_length=2000)


@router.put("/radiograph-comparisons")
def save_comparison(body: ComparisonIn, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> dict:
    """Le médecin qualifie l'évolution entre deux clichés du même patient (ordre chronologique imposé)."""
    a, b = _owned_doc(db, body.document_a_id, user), _owned_doc(db, body.document_b_id, user)
    if a.id == b.id or a.patient_id != b.patient_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Deux radiographies différentes du même patient.")
    if (a.exam_date or a.created_at.date()) > (b.exam_date or b.created_at.date()):
        a, b = b, a
    c = db.scalar(select(RadiographComparison).where(RadiographComparison.document_a_id == a.id,
                                                     RadiographComparison.document_b_id == b.id))
    if c is None:
        c = RadiographComparison(patient_id=a.patient_id, document_a_id=a.id, document_b_id=b.id, created_by=user.id)
        db.add(c)
    c.qualification, c.comment, c.updated_at = body.qualification, (body.comment or "").strip() or None, utcnow()
    c.created_by = user.id
    db.commit()
    audit(db, user.id, "radiograph_comparison", "patient", a.patient_id,
          {"a": str(a.id), "b": str(b.id), "qualification": c.qualification})
    return _cmp_out(c)


# ---------------------------------------------------------------- F-C8 : recalage et carte de différence
def _difference(db: Session, a_id: uuid.UUID, b_id: uuid.UUID, user: User) -> tuple[Path, dict]:
    """Carte (cliché ancien + différence) et paramètres du recalage, calculés une fois puis mis en cache."""
    a, b = _owned_doc(db, a_id, user), _owned_doc(db, b_id, user)
    if a.id == b.id or a.patient_id != b.patient_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Deux radiographies différentes du même patient.")
    if (a.exam_date or a.created_at.date()) > (b.exam_date or b.created_at.date()):
        a, b = b, a
    png = storage.absolute(a.file_path).with_name(f"{a.id}.diff.{b.id}.png")
    meta = png.with_suffix(".json")
    if not (png.exists() and meta.exists()):
        r = registration.register(storage.absolute(a.file_path), storage.absolute(b.file_path))
        base = Image.open(storage.absolute(a.file_path)).convert("RGBA")
        base.thumbnail((1024, 1024))
        over = Image.open(io.BytesIO(r.png)).resize(base.size)
        buf = io.BytesIO()
        Image.alpha_composite(base, over).convert("RGB").save(buf, "PNG")
        png.write_bytes(buf.getvalue())
        meta.write_text(json.dumps({"older": str(a.id), "newer": str(b.id), "angle": r.angle, "scale": r.scale,
                                    "ncc_before": r.ncc_before, "ncc_after": r.ncc_after, "reliable": r.reliable}))
    return png, json.loads(meta.read_text())


@router.get("/documents/{document_id}/difference/{other_id}")
def difference(document_id: uuid.UUID, other_id: uuid.UUID, user: User = Depends(require_doctor),
               db: Session = Depends(get_db)) -> dict:
    _, info = _difference(db, document_id, other_id, user)
    audit(db, user.id, "imaging_difference", "document", uuid.UUID(info["older"]), {"newer": info["newer"]})
    return info


@router.get("/documents/{document_id}/difference/{other_id}/image")
def difference_image(document_id: uuid.UUID, other_id: uuid.UUID, user: User = Depends(require_doctor),
                     db: Session = Depends(get_db)) -> Response:
    png, _ = _difference(db, document_id, other_id, user)
    return Response(png.read_bytes(), media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
