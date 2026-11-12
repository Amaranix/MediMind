"""Dossier de faits de la fiche pré-consultation (F-E2, étape 1).

Tous les faits sont calculés par le code à partir des seules données validées par le médecin ; chacun porte
sa référence (mesure, document). La fiche (gabarit ou reformulation LLM) ne peut citer que ces faits.

- Dernières valeurs : la plus récente de chaque paramètre, son ancienneté (jours) et sa variation depuis la mesure
  précédente ; une valeur ancienne (gaz du sang d'une hospitalisation...) reste listée, à la fiche de la situer.
- Tendances : sur les 12 mois précédant la dernière donnée (Theil-Sen, qualification du référentiel).
- Alertes : celles qui portent sur la donnée la plus récente ; une alerte non acquittée devient un point à aborder.
- Traitements : en cours à la date de la fiche, et dernier changement de traitement de fond.
- Radiographies : les deux dernières vues de face analysées ; variation des scores et marge d'incertitude (T29),
  sans verdict d'évolution (D5).
"""
from __future__ import annotations

import datetime as dt
import math
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Alert,
    AlertState,
    Document,
    DocumentType,
    Imaging,
    Measurement,
    Patient,
    Treatment,
    ValidationStatus,
)
from app.schemas import age_on
from app.services.alerts import VALIDATED, load_series
from app.services.referential import Referential
from app.services.timeline import Rx, build_bars
from app.services.trends import trends

# Score IA suivi par défaut selon la pathologie (même correspondance que l'interface, T28)
DEFAULT_SCORE = {"bpco": "Emphysema", "fibrose": "Fibrosis", "pneumonie": "Consolidation"}
TREND_WINDOW_DAYS = 365


def within_margin(a: float, ua: float, b: float, ub: float) -> bool:
    """T29 : variation non distinguable du bruit si |Δ| ≤ 2·√(σ₁²+σ₂²) + 0,02."""
    return abs(b - a) <= 2 * math.hypot(ua, ub) + 0.02


def _latest_values(ref: Referential, series: dict, as_of: dt.date) -> list[dict]:
    order = {p.code: i for i, p in enumerate(ref.parameters)}
    out = []
    for code in sorted(series, key=order.__getitem__):
        pts, p = series[code], ref.parameter(code)
        last = pts[-1]
        item = {"param": code, "name": p.name, "unit": p.unit, "date": last.date, "value": last.value,
                "days_old": (as_of - last.date).days,
                "context": list(last.context), "measurement_id": last.measurement_id, "document_id": last.document_id,
                "out_of_range": bool(p.reference and ((p.reference.low is not None and last.value < p.reference.low)
                                                      or (p.reference.high is not None and last.value > p.reference.high))),
                "previous": None}
        if len(pts) > 1:
            prev = pts[-2]
            item["previous"] = {"date": prev.date, "value": prev.value, "delta": round(last.value - prev.value, 4),
                                "measurement_id": prev.measurement_id, "document_id": prev.document_id}
        out.append(item)
    return out


def _trends(ref: Referential, series: dict) -> list[dict]:
    if not series:
        return []
    end = max(pts[-1].date for pts in series.values())
    start = end - dt.timedelta(days=TREND_WINDOW_DAYS)
    window = {k: [p for p in v if p.date >= start] for k, v in series.items()}
    keep = []
    for t in trends(ref, window):
        if t["qualification"] == "insufficient":
            continue
        pts = window[t["param"]]
        keep.append({**t, "name": ref.parameter(t["param"]).name,
                     "measurement_ids": [p.measurement_id for p in pts], "document_ids": sorted(
                         {p.document_id for p in pts if p.document_id})})
    return keep


def _alerts(db: Session, ref: Referential, patient_id: uuid.UUID) -> list[dict]:
    rules = {r.id: r for r in ref.alert_rules}
    out = []
    for a in db.scalars(select(Alert).where(Alert.patient_id == patient_id, Alert.current.is_(True))
                        .order_by(Alert.date.desc())):
        r = rules.get(a.rule_id)
        out.append({"id": str(a.id), "rule_id": a.rule_id, "label": r.label if r else a.rule_id,
                    "severity": r.severity if r else "info", "source": r.source if r else None, "date": a.date,
                    "state": a.state.value, "message": a.message, "values": (a.source_values or {}).get("values", []),
                    "ruleset_version": a.ruleset_version})
    return sorted(out, key=lambda x: x["severity"] != "warning")


def _treatments(db: Session, patient_id: uuid.UUID, as_of: dt.date) -> tuple[list[dict], dict | None]:
    rx = [Rx(t.molecule, t.drug_class, t.dosage, t.start_date, t.duration_days,
             str(t.source_document_id) if t.source_document_id else None)
          for t in db.scalars(select(Treatment).where(Treatment.patient_id == patient_id,
                                                      Treatment.validation_status.in_(VALIDATED)))]
    bars, changes = build_bars(rx)
    current = [{"molecule": b.molecule, "drug_class": b.drug_class, "dosage": b.dosage, "start": b.start,
                "end": b.end, "long_term": b.long_term, "document_ids": b.documents}
               for b in bars if b.start <= as_of and (b.end is None or b.end >= as_of)]
    past = [c for c in changes if c["date"] <= as_of]
    return current, (past[-1] if past else None)


def _radiographs(db: Session, patient: Patient) -> dict | None:
    rows = db.execute(select(Document, Imaging).join(Imaging, Imaging.document_id == Document.id)
                      .where(Document.patient_id == patient.id, Document.type == DocumentType.radiographie,
                             Document.exam_date.is_not(None), Imaging.scores.is_not(None))
                      .order_by(Document.exam_date)).all()
    face = [(d, im) for d, im in rows if im.view != "profil"]
    if not face:
        return None
    pathologies = [DEFAULT_SCORE[c] for c in patient.conditions or [] if c in DEFAULT_SCORE] or ["Consolidation"]
    items = [{"document_id": str(d.id), "date": d.exam_date, "model_name": im.model_name,
              "model_version": im.model_version, "quality_flags": [f for f in (im.quality_flag or "").split(",") if f],
              "doctor_assessment": im.doctor_assessment} for d, im in face[-2:]]
    comparisons = []
    if len(face) > 1:
        (_, a), (_, b) = face[-2], face[-1]
        for p in pathologies:
            if p in a.scores and p in b.scores:
                ua, ub = (a.uncertainty or {}).get(p, 0.0), (b.uncertainty or {}).get(p, 0.0)
                comparisons.append({"pathology": p, "before": a.scores[p], "after": b.scores[p],
                                    "uncertainty_before": ua, "uncertainty_after": ub,
                                    "delta": round(b.scores[p] - a.scores[p], 4),
                                    "within_margin": within_margin(a.scores[p], ua, b.scores[p], ub)})
    return {"count": len(face), "items": items, "comparisons": comparisons}


def build_facts(db: Session, ref: Referential, patient: Patient, as_of: dt.date | None = None) -> dict:
    as_of = as_of or dt.date.today()
    series = load_series(db, patient.id)
    alerts = _alerts(db, ref, patient.id)
    current_rx, last_change = _treatments(db, patient.id, as_of)
    pending = db.scalar(select(func.count()).select_from(Measurement).where(
        Measurement.patient_id == patient.id,
        Measurement.validation_status.in_((ValidationStatus.pending, ValidationStatus.suspect)))) or 0
    last_data = max((pts[-1].date for pts in series.values()), default=None)

    points = [{"kind": "alert", "text": f"{a['label']} : {a['message']}", "alert_id": a["id"],
               "values": a["values"]} for a in alerts if a["state"] == AlertState.open.value]
    if pending:
        points.append({"kind": "pending", "text": f"{pending} valeur(s) en attente de validation, non prises en compte",
                       "count": pending})

    return {
        "as_of": as_of,
        "ruleset_version": ref.version,
        "patient": {"id": str(patient.id), "age": age_on(patient.birth_date, as_of), "sex": patient.sex.value,
                    "conditions": [{"code": c, "label": ref.conditions.get(c, c)} for c in patient.conditions or []],
                    "pack_years": patient.pack_years, "antecedents": patient.antecedents,
                    "allergies": patient.allergies},
        "reason": "Suivi : " + ", ".join(ref.conditions.get(c, c) for c in patient.conditions or [])
                  if patient.conditions else "Suivi pneumologique",
        "last_data_date": last_data,
        "latest_values": _latest_values(ref, series, as_of),
        "trends": _trends(ref, series),
        "alerts": alerts,
        "treatments": {"current": current_rx, "last_change": last_change},
        "radiographs": _radiographs(db, patient),
        "points_to_discuss": points,
    }
