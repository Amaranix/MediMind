"""Fiche pré-consultation par gabarit (F-E1) : dossier de faits -> HTML (Jinja2) -> PDF A4 (PyMuPDF).

Le gabarit ne reçoit que le dossier de faits, le nom affiché et les métadonnées des documents cités : aucun
chiffre n'est produit ailleurs que dans `facts.py`. Les sources sont numérotées dans l'ordre de citation.
PDF rendu par le moteur HTML de PyMuPDF (déjà utilisé pour l'ingestion) : pas de dépendance système en plus (T32).
"""
from __future__ import annotations

import datetime as dt
import io
import uuid
from pathlib import Path

import jinja2
import pymupdf
from markupsafe import Markup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, Patient
from app.services.referential import Referential

TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATES), autoescape=True, trim_blocks=True,
                         lstrip_blocks=True, undefined=jinja2.StrictUndefined)
RECENT_DAYS = 183  # au-delà, une « dernière valeur » est listée à part comme ancienne

DOC_TYPES = {"bilan_bio": "Bilan biologique", "efr": "EFR", "compte_rendu": "Compte rendu",
             "ordonnance": "Ordonnance", "radiographie": "Radiographie", "inconnu": "Document"}
EVENTS = {"exacerbation": "Exacerbation", "hospitalisation": "Hospitalisation", "pneumonie": "Pneumonie",
          "treatment_change": "Changement de traitement", "autre": "Événement"}
PATHOLOGIES = {"Emphysema": "d'emphysème", "Fibrosis": "de fibrose", "Consolidation": "de consolidation"}
CONTEXTS = {"pre_bd": "pré-BD", "post_bd": "post-BD", "rest": "repos", "exercise": "effort",
            "room_air": "air ambiant", "oxygen": "sous O2"}
TRENDS = {"improving": "Amélioration", "worsening": "Dégradation", "stable": "Stable"}

CSS = """
body { font-family: sans-serif; font-size: 8.6pt; color: #1b1f24; }
h1 { font-size: 14pt; margin: 0; }
h2 { font-size: 10pt; margin: 7pt 0 2pt 0; border-bottom: 1px solid #9aa3ad; }
p, li { margin: 1pt 0; }
ul, ol { margin: 1pt 0; }
.meta { color: #55606b; margin-bottom: 4pt; }
.warn { border: 1px solid #1b1f24; padding: 3pt 5pt; }
.dim { color: #6b7580; }
sup { color: #0f6e6e; font-weight: bold; }
table { border-collapse: collapse; width: 100%; }
th { text-align: left; color: #55606b; }
th, td { padding: 1pt 4pt 1pt 0; border-bottom: 1px solid #e3e7ea; }
.num { text-align: right; }
.sources { margin-top: 6pt; border-top: 1px solid #9aa3ad; color: #55606b; font-size: 7.6pt; }
"""


def fnum(v: float) -> str:
    """Nombre au format français, sans zéros inutiles (même règle que les messages d'alerte)."""
    return f"{v:.3f}".rstrip("0").rstrip(".").replace(".", ",").replace("-", "−")


def fdate(d: dt.date | str) -> str:
    return (dt.date.fromisoformat(d) if isinstance(d, str) else d).strftime("%d/%m/%Y")


ENV.filters.update(
    n=fnum, d=fdate,
    s=lambda v: ("+" if v > 0 else "") + fnum(v),
    u=lambda unit: "" if unit in ("ratio", "pH") else (" %" if unit == "%" else f" {unit}"),
    du=lambda unit: "" if unit in ("ratio", "pH") else (" pts" if unit == "%" else f" {unit}"),
)


def render_html(db: Session, ref: Referential, patient: Patient, facts: dict, generated_at: dt.datetime) -> str:
    ids: dict[str, int] = {}

    def cite(*doc_ids: str | None) -> Markup:
        """Numéro(s) de source en exposant ; plusieurs documents : « 4,5 »."""
        nums = sorted({ids.setdefault(i, len(ids) + 1) for i in doc_ids if i})
        return Markup(f"<sup>{','.join(map(str, nums))}</sup>") if nums else Markup("")

    def sources() -> list[str]:
        docs = {str(d.id): d for d in db.scalars(select(Document).where(
            Document.id.in_([uuid.UUID(i) for i in ids])))} if ids else {}
        out = []
        for doc_id in ids:
            d = docs.get(doc_id)
            out.append(f"{DOC_TYPES.get(d.type.value, 'Document')} du {fdate(d.exam_date)} ({d.original_name})"
                       if d and d.exam_date else (d.original_name if d else "Document supprimé"))
        return out

    trends = {t["param"]: t for t in facts["trends"]}

    def trend(code: str) -> str:
        t = trends.get(code)
        if not t:
            return "Moins de 3 mesures"
        label = TRENDS[t["qualification"]]
        if t["qualification"] == "stable" or t["slope_per_year"] is None:
            return label
        slope = float(f"{t['slope_per_year']:.3g}")  # 3 chiffres significatifs : -0,125 L/an, -10 pts/an
        return f"{label}, {fnum(slope)}{ENV.filters['du'](t['unit'])}/an"

    latest = facts["latest_values"]
    return ENV.get_template("sheet.html").render(
        f=facts, name=f"{patient.first_name} {patient.last_name[:1]}.", generated_at=generated_at,
        recent=[v for v in latest if v["days_old"] <= RECENT_DAYS],
        old=[v for v in latest if v["days_old"] > RECENT_DAYS],
        ref=cite, sources=sources, trend=trend, ctx=lambda c: CONTEXTS.get(c, ref.contexts.get(c, c)),
        event_label=lambda t: EVENTS.get(t, "Événement"), pathology=lambda p: PATHOLOGIES.get(p, p),
    )


def render_pdf(html: str) -> tuple[bytes, int]:
    """PDF A4 et nombre de pages (la fiche doit tenir sur une page)."""
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    story = pymupdf.Story(html, user_css=CSS)
    page = pymupdf.paper_rect("a4")
    pages, more = 0, True
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(page + (36, 32, -36, -32))
        story.draw(dev)
        writer.end_page()
        pages += 1
    writer.close()
    return buf.getvalue(), pages
