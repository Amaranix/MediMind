"""Pipeline d'ingestion pur (sans base de données) : fichier -> type, date, valeurs normalisées.

Utilisé par la tâche de fond `ingest_document` et par le script d'évaluation (evaluation/run_extraction_eval.py).
"""
from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.services import llm
from app.services.ingestion.classify import Classification, classify_rules
from app.services.ingestion.clinical import ExtractedEvent, ExtractedTreatment, extract_events, extract_treatments
from app.services.ingestion.extract import (
    ExtractedValue,
    _finish,
    extract_efr,
    extract_lab,
    extract_report,
    find_exam_date,
)
from app.services.ingestion.normalize import parse_number
from app.services.ingestion.text import DocumentText, extract
from app.services.referential import Referential

EXTRACTORS = {"bilan_bio": extract_lab, "efr": extract_efr, "compte_rendu": extract_report}


@dataclass
class IngestionResult:
    doc_type: str
    type_confidence: float
    type_method: str
    exam_date: dt.date | None
    text: DocumentText
    values: list[ExtractedValue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    treatments: list[ExtractedTreatment] = field(default_factory=list)
    events: list[ExtractedEvent] = field(default_factory=list)
    seconds: float = 0.0


def llm_fallback_values(doc: DocumentText, ref: Referential) -> list[ExtractedValue]:
    """Repli LLM sur texte libre, avec contrôle : la valeur doit figurer littéralement dans le texte."""
    allowed = [p.code for p in ref.parameters]
    out = []
    text = doc.text
    for item in llm.extract_values(text, allowed):
        raw = str(item.get("value", "")).strip()
        parsed = parse_number(raw)
        if not parsed or raw not in text or item.get("param") not in allowed:
            continue
        ev = _finish(ref, item["param"], parsed[0], item.get("unit"), [], 0.5, None, raw, ["llm"])
        if ev:
            out.append(ev)
    return out


def ingest_file(path: Path, mime: str, ref: Referential, *, use_llm: bool = True) -> IngestionResult:
    t0 = time.perf_counter()
    doc = extract(path, mime)
    cls: Classification = classify_rules(doc)
    warnings: list[str] = []
    if cls.type == "inconnu" and use_llm and doc.words:
        guess = llm.classify_document(doc.text)
        if guess:
            cls = Classification(guess[0], min(guess[1], 0.7), "llm", cls.scores)
    if cls.type == "inconnu":
        warnings.append("Type de document non reconnu : à préciser par le médecin.")
    values = EXTRACTORS[cls.type](doc, ref) if cls.type in EXTRACTORS else []
    if not values and cls.type == "compte_rendu" and use_llm:
        values = llm_fallback_values(doc, ref)
    if doc.ocr and doc.mean_conf < 0.6:
        warnings.append("Qualité de lecture faible (scan ou photo) : vérifier chaque valeur.")
    exam_date = find_exam_date(doc)
    treatments = extract_treatments(doc, ref) if cls.type == "ordonnance" else []
    events = extract_events(doc, exam_date) if cls.type == "compte_rendu" else []
    if cls.type == "ordonnance" and not treatments:
        warnings.append("Aucun médicament reconnu dans cette ordonnance.")
    return IngestionResult(cls.type, cls.confidence, cls.method, exam_date, doc, values, warnings,
                           seconds=round(time.perf_counter() - t0, 2), treatments=treatments, events=events)
