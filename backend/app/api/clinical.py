"""Évolution du patient : séries (F-B1/B2), tendances (F-B4), alertes (F-B5), traitements et événements
(F-D1, F-D2, F-D4, F-B3). Seules les données validées par le médecin alimentent courbes, tendances et alertes."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_patient_for_doctor, require_doctor
from app.db.models import (
    Alert,
    AlertState,
    ClinicalEvent,
    Document,
    DocumentType,
    Measurement,
    Patient,
    Treatment,
    User,
    ValidationStatus,
    utcnow,
)
from app.db.session import get_db
from app.services import alerts as alert_engine
from app.services.audit import audit
from app.services.facts import build_facts
from app.services.ingestion.job import refresh_document_status
from app.services.periods import compare_periods
from app.services.referential import get_referential
from app.services.timeline import Rx, build_bars
from app.services.trends import in_series, trends

router = APIRouter(tags=["clinical"])
VALIDATED = (ValidationStatus.validated, ValidationStatus.corrected)
OPEN = (ValidationStatus.pending, ValidationStatus.suspect)
EVENT_TYPES = {"exacerbation", "hospitalisation", "pneumonie", "treatment_change", "autre"}


def recompute_alerts(db: Session, patient_id: uuid.UUID) -> None:
    alert_engine.recompute(db, get_referential(), patient_id)


# ---------------------------------------------------------------- séries et tendances
@router.get("/patients/{patient_id}/series")
def series(params: str | None = Query(None, description="Codes séparés par des virgules"),
           date_from: dt.date | None = Query(None, alias="from"), date_to: dt.date | None = Query(None, alias="to"),
           patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> dict:
    ref = get_referential()
    codes = {c for c in params.split(",") if c} if params else None
    q = select(Measurement).where(Measurement.patient_id == patient.id,
                                  Measurement.validation_status != ValidationStatus.rejected)
    if codes:
        q = q.where(Measurement.parameter_code.in_(codes))
    if date_from:
        q = q.where(Measurement.date >= date_from)
    if date_to:
        q = q.where(Measurement.date <= date_to)
    out: dict[str, dict] = {}
    for m in db.scalars(q.order_by(Measurement.date)):
        if not in_series(m.parameter_code, m.context or []):
            continue
        p = ref.parameter(m.parameter_code)
        s = out.setdefault(p.code, {"code": p.code, "name": p.name, "unit": p.unit, "category": p.category,
                                    "reference": p.reference.model_dump() if p.reference else None,
                                    "points": [], "pending": []})
        item = {"id": str(m.id), "date": m.date, "value": m.value, "context": m.context,
                "document_id": str(m.source_document_id) if m.source_document_id else None,
                "status": m.validation_status.value}
        (s["points"] if m.validation_status in VALIDATED else s["pending"]).append(item)
    order = {p.code: i for i, p in enumerate(ref.parameters)}
    return dict(sorted(out.items(), key=lambda kv: order[kv[0]]))


@router.get("/patients/{patient_id}/trends")
def patient_trends(date_from: dt.date | None = Query(None, alias="from"), date_to: dt.date | None = Query(None, alias="to"),
                   patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> list[dict]:
    data = alert_engine.load_series(db, patient.id)
    window = {k: [p for p in v if (not date_from or p.date >= date_from) and (not date_to or p.date <= date_to)]
              for k, v in data.items()}
    return trends(get_referential(), window)


# ---------------------------------------------------------------- dossier de faits (fiche pré-consultation)
@router.get("/patients/{patient_id}/facts")
def patient_facts(as_of: dt.date | None = Query(None), patient: Patient = Depends(get_patient_for_doctor),
                  user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> dict:
    facts = build_facts(db, get_referential(), patient, as_of)
    audit(db, user.id, "facts_read", "patient", patient.id)
    return facts


@router.get("/patients/{patient_id}/periods")
def periods(a_from: dt.date, a_to: dt.date, b_from: dt.date, b_to: dt.date,
            patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> list[dict]:
    """F-B8 : comparaison de deux périodes (mesures validées)."""
    if a_from > a_to or b_from > b_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Chaque période doit commencer avant de finir.")
    return compare_periods(get_referential(), alert_engine.load_series(db, patient.id), (a_from, a_to), (b_from, b_to))


# ---------------------------------------------------------------- frise
@router.get("/patients/{patient_id}/timeline")
def timeline(patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> dict:
    rx = [Rx(t.molecule, t.drug_class, t.dosage, t.start_date, t.duration_days,
             str(t.source_document_id) if t.source_document_id else None)
          for t in db.scalars(select(Treatment).where(Treatment.patient_id == patient.id,
                                                      Treatment.validation_status.in_(VALIDATED)))]
    bars, changes = build_bars(rx)
    events = db.scalars(select(ClinicalEvent).where(ClinicalEvent.patient_id == patient.id,
                                                    ClinicalEvent.validation_status.in_(VALIDATED))
                        .order_by(ClinicalEvent.date))
    radios = db.scalars(select(Document).where(Document.patient_id == patient.id,
                                               Document.type == DocumentType.radiographie)
                        .order_by(Document.exam_date))
    return {
        "treatments": [vars(b) for b in bars],
        "treatment_changes": changes,
        "events": [{"id": str(e.id), "type": e.type, "date": e.date, "end_date": e.end_date, "note": e.note,
                    "document_id": str(e.source_document_id) if e.source_document_id else None} for e in events],
        "radiographs": [{"document_id": str(d.id), "date": d.exam_date, "name": d.original_name}
                        for d in radios if d.exam_date],
    }


# ---------------------------------------------------------------- alertes
@router.get("/patients/{patient_id}/alerts")
def list_alerts(scope: str = Query("open", pattern="^(open|current|all)$"),
                patient: Patient = Depends(get_patient_for_doctor), db: Session = Depends(get_db)) -> list[dict]:
    ref = get_referential()
    rules = {r.id: r for r in ref.alert_rules}
    q = select(Alert).where(Alert.patient_id == patient.id)
    if scope in ("open", "current"):
        q = q.where(Alert.current.is_(True))
    if scope == "open":
        q = q.where(Alert.state == AlertState.open)
    out = []
    for a in db.scalars(q.order_by(Alert.date.desc())):
        r = rules.get(a.rule_id)
        out.append({"id": str(a.id), "rule_id": a.rule_id, "label": r.label if r else a.rule_id,
                    "severity": r.severity if r else "info", "source": r.source if r else None,
                    "note": r.note if r else None, "date": a.date, "current": a.current, "state": a.state.value,
                    "message": a.message, "values": (a.source_values or {}).get("values", []),
                    "ruleset_version": a.ruleset_version, "acknowledged_at": a.acknowledged_at})
    severity = {"warning": 0, "info": 1}
    return sorted(out, key=lambda x: (severity.get(x["severity"], 2), -x["date"].toordinal()))


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> dict:
    a = db.get(Alert, alert_id)
    if a is None or db.get(Patient, a.patient_id).doctor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerte introuvable.")
    a.state, a.acknowledged_by, a.acknowledged_at = AlertState.acknowledged, user.id, utcnow()
    db.commit()
    audit(db, user.id, "alert_acknowledge", "alert", a.id, {"rule_id": a.rule_id})
    return {"id": str(a.id), "state": a.state.value}


# ---------------------------------------------------------------- traitements et événements à valider
def _owned(db: Session, model, obj_id: uuid.UUID, user: User):
    obj = db.get(model, obj_id)
    if obj is None or db.get(Patient, obj.patient_id).doctor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Élément introuvable.")
    return obj


def _treatment_out(t: Treatment) -> dict:
    return {"id": str(t.id), "molecule": t.molecule, "drug_class": t.drug_class, "dosage": t.dosage,
            "start_date": t.start_date, "end_date": t.end_date, "duration_days": t.duration_days,
            "confidence": t.confidence, "bbox": t.bbox, "source_text": t.source_text, "flags": t.flags or [],
            "validation_status": t.validation_status.value}


def _event_out(e: ClinicalEvent) -> dict:
    return {"id": str(e.id), "type": e.type, "date": e.date, "end_date": e.end_date, "note": e.note,
            "confidence": e.confidence, "bbox": e.bbox, "validation_status": e.validation_status.value,
            "manual": e.source_document_id is None}


@router.get("/documents/{document_id}/clinical")
def document_clinical(document_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> dict:
    doc = _owned(db, Document, document_id, user)
    return {"treatments": [_treatment_out(t) for t in db.scalars(select(Treatment).where(
                Treatment.source_document_id == doc.id).order_by(Treatment.molecule))],
            "events": [_event_out(e) for e in db.scalars(select(ClinicalEvent).where(
                ClinicalEvent.source_document_id == doc.id).order_by(ClinicalEvent.date))]}


class TreatmentAction(BaseModel):
    action: str = Field(pattern="^(validate|correct|reject|reset)$")
    molecule: str | None = Field(default=None, max_length=120)
    dosage: str | None = Field(default=None, max_length=255)
    duration_days: int | None = Field(default=None, ge=1, le=3650)
    long_term: bool | None = None


def _decide(obj, action: str, user: User) -> None:
    obj.validation_status = {"validate": ValidationStatus.validated, "correct": ValidationStatus.corrected,
                             "reject": ValidationStatus.rejected, "reset": ValidationStatus.pending}[action]
    obj.validated_by = None if action == "reset" else user.id
    obj.validated_at = None if action == "reset" else utcnow()


@router.patch("/treatments/{treatment_id}")
def act_on_treatment(treatment_id: uuid.UUID, body: TreatmentAction, user: User = Depends(require_doctor),
                     db: Session = Depends(get_db)) -> dict:
    t = _owned(db, Treatment, treatment_id, user)
    before = _treatment_out(t)
    if body.action == "correct":
        if body.molecule:
            t.molecule = body.molecule.strip().lower()
        if body.dosage is not None:
            t.dosage = body.dosage
        if body.long_term:
            t.duration_days, t.end_date = None, None
        elif body.duration_days:
            t.duration_days = body.duration_days
            t.end_date = t.start_date + dt.timedelta(days=body.duration_days)
    _decide(t, body.action, user)
    if t.source_document_id:
        refresh_document_status(db, db.get(Document, t.source_document_id))
    recompute_alerts(db, t.patient_id)
    db.commit()
    audit(db, user.id, f"treatment_{body.action}", "treatment", t.id,
          {"before": {k: str(v) for k, v in before.items() if k in ("molecule", "dosage", "duration_days")},
           "after": {"molecule": t.molecule, "dosage": t.dosage, "duration_days": t.duration_days}})
    return _treatment_out(t)


class EventIn(BaseModel):
    type: str
    date: dt.date
    end_date: dt.date | None = None
    note: str | None = Field(default=None, max_length=1000)


class EventAction(BaseModel):
    action: str = Field(pattern="^(validate|correct|reject|reset)$")
    date: dt.date | None = None
    end_date: dt.date | None = None
    note: str | None = Field(default=None, max_length=1000)


@router.post("/patients/{patient_id}/events", status_code=status.HTTP_201_CREATED)
def add_event(body: EventIn, patient: Patient = Depends(get_patient_for_doctor), user: User = Depends(require_doctor),
              db: Session = Depends(get_db)) -> dict:
    """Événement saisi par le médecin : validé d'emblée."""
    if body.type not in EVENT_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Type d'événement inconnu.")
    if body.date > dt.date.today() or (body.end_date and body.end_date < body.date):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Dates incohérentes.")
    e = ClinicalEvent(patient_id=patient.id, type=body.type, date=body.date, end_date=body.end_date, note=body.note,
                      created_by=user.id, validation_status=ValidationStatus.validated, validated_by=user.id,
                      validated_at=utcnow(), confidence=1.0)
    db.add(e)
    db.commit()
    audit(db, user.id, "event_create", "event", e.id, {"type": e.type})
    return _event_out(e)


@router.patch("/events/{event_id}")
def act_on_event(event_id: uuid.UUID, body: EventAction, user: User = Depends(require_doctor),
                 db: Session = Depends(get_db)) -> dict:
    e = _owned(db, ClinicalEvent, event_id, user)
    if body.action == "correct":
        e.date = body.date or e.date
        e.end_date = body.end_date if body.end_date is not None else e.end_date
        e.note = body.note if body.note is not None else e.note
    _decide(e, body.action, user)
    if e.source_document_id:
        refresh_document_status(db, db.get(Document, e.source_document_id))
    db.commit()
    audit(db, user.id, f"event_{body.action}", "event", e.id)
    return _event_out(e)


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_event(event_id: uuid.UUID, user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> Response:
    e = _owned(db, ClinicalEvent, event_id, user)
    if e.source_document_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un événement extrait d'un document se rejette, il ne se supprime pas.")
    db.delete(e)
    db.commit()
    audit(db, user.id, "event_delete", "event", event_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
