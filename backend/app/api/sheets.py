"""Fiche pré-consultation (F-E1) : génération par gabarit, aperçu HTML et PDF A4, conservée avec ses faits."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_patient_for_doctor, require_doctor
from app.db.models import ConsultationSheet, Patient, User, utcnow
from app.db.session import get_db
from app.services import storage
from app.services.audit import audit
from app.services.facts import build_facts
from app.services.referential import get_referential
from app.services.sheet import CSS, render_html, render_pdf

router = APIRouter(tags=["sheets"])


def _out(s: ConsultationSheet) -> dict:
    page = f"<!doctype html><meta charset='utf-8'><style>{CSS} body {{ margin: 28px 36px; }}</style>{s.text}"
    return {"id": str(s.id), "created_at": s.created_at, "mode": s.mode, "html": page,
            "pages": (s.verification or {}).get("pages"), "as_of": s.facts.get("as_of")}


@router.post("/patients/{patient_id}/sheets", status_code=status.HTTP_201_CREATED)
def create_sheet(as_of: dt.date | None = Query(None), patient: Patient = Depends(get_patient_for_doctor),
                 user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> dict:
    ref = get_referential()
    facts = build_facts(db, ref, patient, as_of)
    now = utcnow()
    html = render_html(db, ref, patient, facts, now.astimezone())
    pdf, pages = render_pdf(html)
    sheet = ConsultationSheet(id=uuid.uuid4(), patient_id=patient.id, created_at=now, facts=jsonable_encoder(facts),
                              text=html, mode="template", verification={"pages": pages})
    sheet.pdf_path = storage.save(patient.id, sheet.id, "sheet.pdf", pdf)
    db.add(sheet)
    db.commit()
    audit(db, user.id, "sheet_create", "patient", patient.id, {"sheet_id": str(sheet.id), "pages": pages})
    return _out(sheet)


@router.get("/sheets/{sheet_id}/pdf")
def sheet_pdf(sheet_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> Response:
    s = db.get(ConsultationSheet, sheet_id)
    if s is None or db.get(Patient, s.patient_id).doctor_id != user.id or not s.pdf_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fiche introuvable.")
    audit(db, user.id, "sheet_download", "patient", s.patient_id, {"sheet_id": str(s.id)})
    name = f"fiche-pre-consultation-{s.created_at:%Y%m%d}.pdf"
    return Response(storage.absolute(s.pdf_path).read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
