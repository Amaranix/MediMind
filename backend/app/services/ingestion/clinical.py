"""Extraction des traitements (F-D1, ordonnances) et des événements cliniques (F-D4, comptes rendus).

Règles uniquement : une molécule n'est reconnue que si elle figure dans les classes de traitements du
référentiel (DCI), éventuellement avec une faute d'OCR. Les associations « a/b » sont gardées ensemble.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.services.ingestion.extract import DATE, TextIndex, _to_date
from app.services.ingestion.normalize import fold
from app.services.ingestion.text import DocumentText, group_lines
from app.services.referential import Referential


@dataclass
class ExtractedTreatment:
    molecule: str
    drug_class: str
    dosage: str | None
    duration_days: int | None
    confidence: float
    bbox: dict | None
    source_text: str
    flags: list[str] = field(default_factory=list)


@dataclass
class ExtractedEvent:
    type: str          # exacerbation | hospitalisation | pneumonie
    date: dt.date | None
    end_date: dt.date | None
    note: str
    confidence: float
    bbox: dict | None


def _molecules(ref: Referential) -> dict[str, tuple[str, str]]:
    """forme pliée -> (DCI affichée, classe)."""
    out = {}
    for cls, names in ref.treatment_classes.items():
        for n in names:
            out[fold(n)] = (n, cls)
    return out


def _match_molecule(token: str, table: dict[str, tuple[str, str]]) -> tuple[str, str, float] | None:
    f = fold(token)
    if f in table:
        return (*table[f], 100.0)
    best = max(table, key=lambda k: fuzz.ratio(k, f))
    score = fuzz.ratio(best, f)
    return (*table[best], score) if score >= 85 and len(f) >= 6 else None


DURATION = re.compile(r"(?:pendant|durant|pour)\s+(\d{1,3})\s*(jours?|j\b|semaines?)", re.I)
LONG_TERM = re.compile(r"(au long cours|traitement de fond|à renouveler|en continu)", re.I)


def extract_treatments(doc: DocumentText, ref: Referential) -> list[ExtractedTreatment]:
    table = _molecules(ref)
    out: list[ExtractedTreatment] = []
    seen: set[str] = set()
    for line in group_lines(doc.words):
        text = line.text
        found = None
        for k in range(min(4, len(line.words))):  # la molécule est en tête de ligne (après un éventuel « 1. »)
            for n in (3, 2, 1):  # « amoxicilline-acide clavulanique » occupe deux mots
                if k + n > len(line.words):
                    continue
                phrase = " ".join(x.text for x in line.words[k:k + n]).strip(".,;:")
                parts = [p for p in re.split(r"[/+]", phrase) if p.strip()]
                matches = [_match_molecule(p, table) for p in parts]
                if matches and all(matches) and (n == 1 or all(m[2] == 100 for m in matches)):
                    found = (k + n - 1, matches)
                    break
            if found:
                break
        if found:
            k, matches = found
            names = "/".join(m[0] for m in matches)
            if names in seen:
                continue
            classes = "+".join(dict.fromkeys(m[1] for m in matches))
            score = min(m[2] for m in matches)
            rest = " ".join(x.text for x in line.words[k + 1:])
            dosage = re.split(r"\.\s*(?:Pendant|Durant|Traitement|À renouveler)", rest, flags=re.I)[0].strip(" .,")
            dur = DURATION.search(text)
            days = None
            if dur:
                days = int(dur.group(1)) * (7 if dur.group(2).lower().startswith("sem") else 1)
            flags = [] if dur or LONG_TERM.search(text) else ["duration_unknown"]
            if score < 100:
                flags.append("molecule_fuzzy")
            conf = (0.97 if not doc.ocr else min(0.9, line.conf)) * score / 100
            if "duration_unknown" in flags:
                conf = min(conf, 0.7)
            seen.add(names)
            out.append(ExtractedTreatment(names, classes, dosage or None, days, round(conf, 3),
                                          line.bbox(), text[:300], flags))
    return out


HOSPITALISATION = re.compile(r"hospitalisation\s+du\s+" + DATE + r"\s+au\s+" + DATE, re.I)


def extract_events(doc: DocumentText, exam_date: dt.date | None) -> list[ExtractedEvent]:
    idx = TextIndex(doc.words)
    text = idx.text
    f = fold(text)
    conf = 0.95 if not doc.ocr else 0.8
    events: list[ExtractedEvent] = []
    m = HOSPITALISATION.search(text)
    if m:
        start, end = _to_date(m), _to_date(m, 3)
        events.append(ExtractedEvent("hospitalisation", start, end, "Hospitalisation", conf,
                                     idx.bbox(m.start(), m.end())))
    elif "exacerbation" in f and exam_date:
        pos = f.find("exacerbation")
        if not re.search(r"(pas d|sans|absence d)\W*\w*\W*exacerbation", f[max(0, pos - 25): pos + 12]):
            k = text.lower().find("exacerbation")
            events.append(ExtractedEvent("exacerbation", exam_date, None, "Exacerbation", conf,
                                         idx.bbox(k, k + 12) if k >= 0 else None))
    if re.search(r"diagnostic retenu\W+pneumonie|pneumonie communautaire", f) and exam_date and not m:
        k = text.lower().find("pneumonie")
        events.append(ExtractedEvent("pneumonie", exam_date, None, "Pneumonie", conf, idx.bbox(k, k + 9)))
    return events
