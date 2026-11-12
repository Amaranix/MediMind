"""Assistant du dossier (F-E4) : questions en langage naturel sur le patient ouvert, réponses citées.

Principe (T36) : aucune phrase n'est rédigée par un LLM. Les valeurs, dates, comptes et traitements sont lus dans
les données validées (requêtes SQL dans l'application, voir `load_patient_data`) et mis en forme par le code ;
chaque réponse cite ses documents. Une question qui ne relève d'aucune de ces familles passe par la recherche
sémantique dans le texte des documents (`search.py`) : on renvoie les passages, jamais une synthèse.

Refus : demande de diagnostic, de prescription ou de conduite à tenir, et toute question sans réponse dans le
dossier (« je ne trouve pas cette information dans le dossier »).

Le cœur (`answer`) travaille sur un `PatientData` : l'évaluation le construit depuis la vérité terrain du
générateur, l'application depuis la base.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ClinicalEvent, Document, Treatment, ValidationStatus
from app.services.alerts import load_series
from app.services.referential import Referential
from app.services.sheet import DOC_TYPES, EVENTS, fdate, fnum
from app.services.trends import Point

VALIDATED = (ValidationStatus.validated, ValidationStatus.corrected)
NEAR_DAYS = 7  # une mesure « à une date » peut être prise jusqu'à 7 jours après (bilan du lendemain)

REFUSE = re.compile(
    r"\b(que|quoi|quel(?:le)?s?)\b.{0,30}\b(prescrire|donner|proposer|faire)\b|\b(dois-je|faut-il|devrais-je|"
    r"recommande[sz]?|conseille[sz]?|conduite a tenir)\b|\bquel est (?:le|son) diagnostic\b|\bdiagnostiquer\b|"
    r"\best-(?:ce|il|elle) (?:une|un|atteint)\b")
DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
EVENT_WORDS = {"exacerbation": "exacerbation", "hospitalisation": "hospitalisation", "pneumonie": "pneumonie"}


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


@dataclass
class Rx:
    molecule: str
    drug_class: str | None
    dosage: str | None
    start: dt.date
    duration_days: int | None
    document_id: str | None


@dataclass
class PatientData:
    series: dict[str, list[Point]]
    events: list[dict]                       # {type, date, end_date, document_id}
    rx: list[Rx]
    docs: dict[str, dict]                    # id -> {type, date, name}
    search: Callable[[str], list[dict]] | None = None   # recherche sémantique (passages)


@dataclass
class Answer:
    kind: str          # value | variation | count | treatment | normalisation | passages | refusal | not_found
    text: str
    citations: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    passages: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------- analyse de la question
def _dates(q: str) -> list[dt.date]:
    out = []
    for d, m, y in DATE.findall(q):
        try:
            out.append(dt.date(int(y), int(m), int(d)))
        except ValueError:
            continue
    return out


def find_param(ref: Referential, q: str) -> str | None:
    """Paramètre cité (synonyme le plus long), basculé vers sa version « % prédit » si la question le demande."""
    best: tuple[int, str] | None = None
    for p in ref.parameters:
        for name in {p.code, p.name, *p.synonyms}:
            n = fold(name)
            if len(n) >= 2 and re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", q) and (best is None or len(n) > best[0]):
                best = (len(n), p.code)
    if best is None:
        return None
    code = best[1]
    if re.search(r"%|pourcentage|predit|theorique", q) and not code.endswith("_PRED"):
        pred = f"{code}_PRED"
        if any(p.code == pred for p in ref.parameters):
            code = pred
    return code


def _unit(unit: str) -> str:
    return "" if unit in ("ratio", "pH") else f" {unit}"


def _fmt_value(v: float, unit: str) -> str:
    return f"{fnum(round(v, 2))}{_unit(unit)}"


def _fmt_delta(d: float, unit: str) -> str:
    sign = "+" if d > 0 else ""
    if unit == "L":
        return f"{sign}{fnum(round(d * 1000))} mL"
    if unit == "%":
        return f"{sign}{fnum(round(d, 1))} points"
    return f"{sign}{fnum(round(d, 2))}{_unit(unit)}"


def _at(points: list[Point], day: dt.date) -> Point | None:
    """Mesure du jour, sinon la plus proche dans les NEAR_DAYS jours suivants."""
    exact = [p for p in points if p.date == day]
    if exact:
        return exact[-1]
    after = [p for p in points if 0 < (p.date - day).days <= NEAR_DAYS]
    return min(after, key=lambda p: p.date) if after else None


def _cite(*pts: Point | None) -> list[str]:
    return [p.document_id for p in pts if p and p.document_id]


# ---------------------------------------------------------------- familles de questions
def _value(ref, data, q, code) -> Answer | None:
    p = ref.parameter(code)
    pts = sorted(data.series.get(code, []), key=lambda x: x.date)
    if not pts:
        return Answer("not_found", f"Aucune valeur validée de {p.name} dans le dossier.")
    dates = _dates(q)
    if len(dates) >= 2 and re.search(r"vari|evolu|difference|ecart|change", q):
        a, b = _at(pts, dates[0]), _at(pts, dates[1])
        if not a or not b:
            missing = dates[0] if not a else dates[1]
            return Answer("not_found", f"Pas de {p.name} validé le {fdate(missing)} (ni dans les {NEAR_DAYS} jours suivants).")
        d = b.value - a.value
        return Answer("variation", f"{p.name} : {_fmt_delta(d, p.unit)} ({_fmt_value(a.value, p.unit)} le {fdate(a.date)}, "
                      f"{_fmt_value(b.value, p.unit)} le {fdate(b.date)}).", _cite(a, b),
                      {"param": code, "delta": round(d, 4), "from": a.date, "to": b.date})
    day = dates[0] if dates else None
    if day is None:
        ev = _event_ref(data, q)
        if ev:
            day = ev["date"]
    if day is not None:
        m = _at(pts, day)
        if not m:
            return Answer("not_found", f"Pas de {p.name} validé le {fdate(day)} (ni dans les {NEAR_DAYS} jours suivants).")
        note = "" if m.date == day else f" (mesure la plus proche, le {fdate(m.date)})"
        return Answer("value", f"{p.name} : {_fmt_value(m.value, p.unit)} le {fdate(m.date)}{note}.", _cite(m),
                      {"param": code, "value": m.value, "date": m.date})
    last = pts[-1]
    prev = pts[-2] if len(pts) > 1 else None
    text = f"Dernière valeur de {p.name} : {_fmt_value(last.value, p.unit)} le {fdate(last.date)}"
    if prev:
        text += f" (précédente : {_fmt_value(prev.value, p.unit)} le {fdate(prev.date)})"
    return Answer("value", text + ".", _cite(last, prev), {"param": code, "value": last.value, "date": last.date})


def _event_ref(data: PatientData, q: str) -> dict | None:
    """« lors de l'exacerbation », « au diagnostic de la pneumonie » : date de l'événement visé."""
    for word, kind in EVENT_WORDS.items():
        if word in q:
            evs = sorted((e for e in data.events if e["type"] == kind), key=lambda e: e["date"])
            if evs:
                return evs[0] if re.search(r"diagnostic|premier|premiere|debut", q) else evs[-1]
    return None


def _count(data: PatientData, q: str) -> Answer | None:
    for word, kind in EVENT_WORDS.items():
        if word in q:
            evs = sorted((e for e in data.events if e["type"] == kind), key=lambda e: e["date"])
            label = EVENTS[kind].lower()
            if not evs:
                return Answer("count", f"Aucune {label} enregistrée dans le dossier.", [], {"count": 0})
            dates = ", ".join(fdate(e["date"]) for e in evs)
            return Answer("count", f"{len(evs)} {label}{'s' if len(evs) > 1 else ''} : {dates}.",
                          [e["document_id"] for e in evs if e["document_id"]], {"count": len(evs)})
    return None


def _normalisation(ref, data, q, code) -> Answer:
    p = ref.parameter(code)
    m = re.search(r"<\s*(\d+(?:[.,]\d+)?)", q)
    threshold = float(m.group(1).replace(",", ".")) if m else (p.reference.high if p.reference else None)
    dates = _dates(q)
    start = dates[0] if dates else next((r.start for r in sorted(data.rx, key=lambda r: r.start)
                                          if r.drug_class == "antibiotic"), None)
    if threshold is None or start is None:
        return Answer("not_found", "Seuil ou date de départ introuvable pour cette question.")
    after = sorted((x for x in data.series.get(code, []) if x.date > start), key=lambda x: x.date)
    hit = next((x for x in after if x.value < threshold), None)
    if hit:
        return Answer("normalisation", f"Oui, le {fdate(hit.date)} ({_fmt_value(hit.value, p.unit)}), première valeur "
                      f"sous {fnum(threshold)}{_unit(p.unit)} après le {fdate(start)}.", _cite(hit),
                      {"normalized": True, "date": hit.date, "value": hit.value})
    last = after[-1] if after else None
    tail = f" Dernière valeur : {_fmt_value(last.value, p.unit)} le {fdate(last.date)}." if last else ""
    return Answer("normalisation", f"Non, aucune valeur sous {fnum(threshold)}{_unit(p.unit)} après le {fdate(start)}.{tail}",
                  _cite(last), {"normalized": False})


def _ids(*rxs: Rx) -> list[str]:
    return [r.document_id for r in rxs if r.document_id]


def _treatment(data: PatientData, q: str) -> Answer | None:
    rx = sorted(data.rx, key=lambda r: r.start)
    antibiotics = [r for r in rx if r.drug_class == "antibiotic"]
    if "relais" in q:
        first = antibiotics[0] if antibiotics else None
        relays = [r for r in antibiotics[1:] if first and r.molecule != first.molecule
                  and (r.start - first.start).days <= (first.duration_days or 0) + 30]
        if not relays:
            return Answer("treatment", "Non : aucun relais antibiotique enregistré.", _ids(*antibiotics[:1]), {"relay": False})
        r = relays[0]
        return Answer("treatment", f"Oui, {r.molecule} le {fdate(r.start)}.", _ids(r),
                      {"relay": True, "molecule": r.molecule, "date": r.start})
    if "antibio" in q:
        if not antibiotics:
            return Answer("treatment", "Aucune antibiothérapie enregistrée.")
        r = antibiotics[0] if re.search(r"diagnostic|premier|initial|debut", q) else antibiotics[-1]
        duration = f", {r.duration_days} jours" if r.duration_days else ""
        return Answer("treatment", f"{r.molecule}{duration} (débutée le {fdate(r.start)}).", _ids(r),
                      {"molecule": r.molecule, "duration_days": r.duration_days, "date": r.start})
    if "antifibros" in q:
        af = [r for r in rx if r.drug_class == "antifibrotic"]
        if not af:
            return Answer("treatment", "Aucun traitement antifibrosant enregistré.")
        return Answer("treatment", f"{af[0].molecule}, le {fdate(af[0].start)}.", _ids(af[0]),
                      {"molecule": af[0].molecule, "date": af[0].start})
    named = [r for r in rx if fold(r.molecule) in q]
    if named:
        r = named[0]
        dosage = f" ({r.dosage})" if r.dosage else ""
        return Answer("treatment", f"{r.molecule} : première prescription le {fdate(r.start)}{dosage}.", _ids(r),
                      {"molecule": r.molecule, "date": r.start})
    if re.search(r"traitement|medicament|ordonnance", q):
        fond = [r for r in rx if not r.duration_days]
        if not fond:
            return Answer("treatment", "Aucun traitement de fond validé dans le dossier.")
        last = max(r.start for r in fond)
        current = sorted({r.molecule for r in fond if r.start == last})
        return Answer("treatment", f"Traitement de fond de la dernière ordonnance ({fdate(last)}) : {', '.join(current)}.",
                      _ids(*[r for r in fond if r.start == last])[:1], {"molecules": current, "date": last})
    return None


# ---------------------------------------------------------------- point d'entrée
def answer(ref: Referential, data: PatientData, question: str) -> Answer:
    q = fold(question.strip())
    if not q:
        return Answer("not_found", "Posez une question sur le dossier du patient.")
    if REFUSE.search(q):
        return Answer("refusal", "Je réponds uniquement à partir du dossier : je ne donne ni diagnostic, ni prescription, "
                      "ni conduite à tenir. Ces décisions reviennent au médecin.")
    code = find_param(ref, q)
    if "combien" in q and any(w in q for w in EVENT_WORDS) and not code and (a := _count(data, q)):
        return a
    if code and "normalis" in q:
        return _normalisation(ref, data, q, code)
    if code:
        return _value(ref, data, q, code)
    if (a := _treatment(data, q)):
        return a
    if data.search:
        hits = data.search(question)
        if hits:
            return Answer("passages", "Passages des documents du dossier les plus proches de la question :",
                          sorted({h["document_id"] for h in hits}), passages=hits)
    return Answer("not_found", "Je ne trouve pas cette information dans le dossier.")


# ---------------------------------------------------------------- données de l'application (requêtes SQL)
def load_patient_data(db: Session, patient_id: uuid.UUID) -> PatientData:
    rx = [Rx(t.molecule, t.drug_class, t.dosage, t.start_date, t.duration_days,
             str(t.source_document_id) if t.source_document_id else None)
          for t in db.scalars(select(Treatment).where(Treatment.patient_id == patient_id,
                                                      Treatment.validation_status.in_(VALIDATED)))]
    events = [{"type": e.type, "date": e.date, "end_date": e.end_date,
               "document_id": str(e.source_document_id) if e.source_document_id else None}
              for e in db.scalars(select(ClinicalEvent).where(ClinicalEvent.patient_id == patient_id,
                                                              ClinicalEvent.validation_status.in_(VALIDATED)))]
    docs = {str(d.id): {"type": DOC_TYPES.get(d.type.value, "Document"), "date": d.exam_date, "name": d.original_name}
            for d in db.scalars(select(Document).where(Document.patient_id == patient_id))}
    return PatientData(load_series(db, patient_id), events, rx, docs)
