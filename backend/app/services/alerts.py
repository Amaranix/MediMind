"""Moteur d'alertes cliniques (F-B5) : applique les règles du référentiel aux données validées.

Chaque alerte cite sa règle, sa source bibliographique (dans le référentiel), la version du référentiel et
les valeurs qui la déclenchent. Une alerte est « actuelle » si elle porte sur la donnée la plus récente du
paramètre concerné ; les autres forment l'historique. Le recalcul conserve les acquittements du médecin.

Types de règles :
- threshold      : valeur comparée à un seuil (contexte de mesure exigé si `require_context`)
- rise           : valeur > seuil ET en hausse par rapport à la mesure précédente
- delta_window   : variation sur une fenêtre (Theil-Sen annualisée, ou première/dernière valeur)
- after_treatment: premier contrôle >= N jours après le début d'un traitement d'une classe donnée
"""
from __future__ import annotations

import datetime as dt
import operator
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alert, AlertState, Measurement, Patient, Treatment, ValidationStatus
from app.services.referential import AlertRule, Referential
from app.services.trends import Point, in_series, theil_sen

OPS = {"<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge}
VALIDATED = (ValidationStatus.validated, ValidationStatus.corrected)


@dataclass
class TreatmentCourse:
    drug_class: str
    start: dt.date
    molecule: str = ""


@dataclass
class AlertCandidate:
    rule_id: str
    date: dt.date
    current: bool
    values: list[dict] = field(default_factory=list)
    message: str = ""


def _fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def _u(unit: str) -> str:
    """Unité affichée après une valeur (le rapport VEMS/CVF n'a pas d'unité)."""
    return "" if unit in ("ratio", "pH") else f" {unit}"


def _du(unit: str) -> str:
    """Unité d'une variation : un écart de pourcentages s'exprime en points."""
    return " points" if unit == "%" else _u(unit)


def _vals(points: list[Point], unit: str) -> list[dict]:
    return [{"date": p.date.isoformat(), "value": p.value, "unit": unit, "measurement_id": p.measurement_id,
             "document_id": p.document_id} for p in points]


def evaluate_rule(rule: AlertRule, ref: Referential, points: list[Point],
                  courses: list[TreatmentCourse]) -> list[AlertCandidate]:
    unit = ref.parameter(rule.param).unit
    pts = sorted((p for p in points if set(rule.require_context) <= set(p.context)), key=lambda p: p.date)
    if not pts:
        return []
    latest = pts[-1].date
    out: list[AlertCandidate] = []
    if rule.type == "threshold":
        for p in pts:
            if OPS[rule.op](p.value, rule.value):
                out.append(AlertCandidate(rule.id, p.date, p.date == latest, _vals([p], unit),
                                          f"{_fmt(p.value)}{_u(unit)} le {p.date:%d/%m/%Y}"))
    elif rule.type == "rise":
        for prev, p in zip(pts, pts[1:], strict=False):
            if p.value > rule.value_gt and p.value > prev.value:
                out.append(AlertCandidate(rule.id, p.date, p.date == latest, _vals([prev, p], unit),
                                          f"{_fmt(prev.value)} puis {_fmt(p.value)}{_u(unit)} le {p.date:%d/%m/%Y}"))
    elif rule.type == "delta_window":
        min_points = rule.min_points or 2
        for end in pts:
            window = [p for p in pts if end.date - dt.timedelta(days=rule.window_days) <= p.date <= end.date]
            if len(window) < min_points or (window[-1].date - window[0].date).days < rule.window_days // 2:
                continue
            if rule.method == "theil_sen":
                slope = theil_sen(window)
                delta = slope * rule.window_days / 365.25 if slope is not None else None
                detail = f"pente {_fmt(delta)}{_du(unit)} sur {rule.window_days // 30} mois ({len(window)} mesures)"
            else:
                delta = window[-1].value - window[0].value
                detail = (f"{_fmt(window[0].value)} le {window[0].date:%d/%m/%Y} puis {_fmt(window[-1].value)} "
                          f"le {window[-1].date:%d/%m/%Y} ({_fmt(delta)}{_du(unit)})")
            if delta is not None and delta <= rule.delta_abs_lte:
                out.append(AlertCandidate(rule.id, end.date, end.date == latest, _vals(window, unit), detail))
    elif rule.type == "after_treatment":
        for c in sorted(courses, key=lambda c: c.start):
            if rule.treatment_class not in c.drug_class.split("+"):
                continue
            ctrl = next((p for p in pts if (p.date - c.start).days >= rule.min_days_after_start), None)
            if ctrl and ctrl.value > rule.value_gt:
                days = (ctrl.date - c.start).days
                msg = (f"{_fmt(ctrl.value)}{_u(unit)} le {ctrl.date:%d/%m/%Y}, "
                       f"{days} jours après le début de {c.molecule or c.drug_class}")
                out.append(AlertCandidate(rule.id, ctrl.date, ctrl.date == latest, _vals([ctrl], unit), msg))
    return out


def evaluate(ref: Referential, series: dict[str, list[Point]], courses: list[TreatmentCourse],
             conditions: list[str] | None = None) -> list[AlertCandidate]:
    """`conditions` : pathologies suivies du patient. Une règle réservée à certaines pathologies
    (ex. critères de progression de fibrose) n'est pas appliquée aux autres patients."""
    out = []
    for rule in ref.alert_rules:
        if rule.conditions and not set(rule.conditions) & set(conditions or []):
            continue
        out += evaluate_rule(rule, ref, series.get(rule.param, []), courses)
    return out


# ---------------------------------------------------------------- base de données
def load_series(db: Session, patient_id: uuid.UUID, codes: set[str] | None = None) -> dict[str, list[Point]]:
    q = select(Measurement).where(Measurement.patient_id == patient_id, Measurement.validation_status.in_(VALIDATED))
    if codes:
        q = q.where(Measurement.parameter_code.in_(codes))
    series: dict[str, list[Point]] = {}
    for m in db.scalars(q.order_by(Measurement.date)):
        ctx = tuple(m.context or [])
        if not in_series(m.parameter_code, ctx):
            continue
        series.setdefault(m.parameter_code, []).append(
            Point(m.date, m.value, ctx, str(m.id), str(m.source_document_id) if m.source_document_id else None))
    return series


def load_courses(db: Session, patient_id: uuid.UUID) -> list[TreatmentCourse]:
    rows = db.scalars(select(Treatment).where(Treatment.patient_id == patient_id,
                                              Treatment.validation_status.in_(VALIDATED)))
    return [TreatmentCourse(t.drug_class or "", t.start_date, t.molecule) for t in rows]


def recompute(db: Session, ref: Referential, patient_id: uuid.UUID) -> list[Alert]:
    """Recalcule les alertes du patient. Les alertes acquittées sont conservées telles quelles."""
    db.flush()
    patient = db.get(Patient, patient_id)
    candidates = evaluate(ref, load_series(db, patient_id), load_courses(db, patient_id), patient.conditions or [])
    existing = {(a.rule_id, a.date): a for a in db.scalars(select(Alert).where(Alert.patient_id == patient_id))}
    keep = set()
    for c in candidates:
        key = (c.rule_id, c.date)
        keep.add(key)
        a = existing.get(key)
        if a is None:
            a = Alert(patient_id=patient_id, rule_id=c.rule_id, date=c.date, state=AlertState.open)
            db.add(a)
        a.ruleset_version, a.current, a.message = ref.version, c.current, c.message
        a.source_values = {"values": c.values}
    for key, a in existing.items():
        if key not in keep:
            db.delete(a)  # la donnée a été rejetée ou corrigée : l'alerte n'a plus lieu d'être
    db.flush()
    return list(db.scalars(select(Alert).where(Alert.patient_id == patient_id)))
