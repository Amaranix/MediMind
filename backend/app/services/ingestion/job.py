"""Tâche de fond `ingest_document` : exécute le pipeline et écrit les mesures « à valider » en base.

Règles :
- la date d'examen saisie par le médecin prime sur la date détectée ; à défaut, date de dépôt + avertissement ;
- le type choisi par le médecin prime sur la classification automatique ;
- une mesure identique déjà présente (paramètre, date, contexte, valeur) n'est pas recréée (dédoublonnage) ;
- une valeur hors bornes plausibles est créée avec le statut `suspect`.
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentStatus,
    DocumentType,
    Job,
    Measurement,
    ValidationStatus,
)
from app.services import storage
from app.services.ingestion.pipeline import ingest_file
from app.services.jobs import register
from app.services.referential import get_referential


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-6, 1e-4 * abs(b))


@register("ingest_document")
def ingest_document(db: Session, job: Job) -> None:
    doc = db.get(Document, uuid.UUID(job.ref_id))
    if doc is None:
        raise LookupError("document supprimé")
    doc.status = DocumentStatus.processing
    db.commit()

    forced_type = doc.type if doc.type_source == "user" else None
    res = ingest_file(storage.absolute(doc.file_path), doc.mime_type, get_referential())
    warnings = list(res.warnings)

    doc.extracted_text = res.text.text
    doc.ocr_boxes = res.text.boxes_json()
    doc.page_count = len(res.text.pages)
    doc.confidence = round(res.text.mean_conf, 3)
    doc.processing_seconds = res.seconds
    if forced_type is None:
        doc.type = DocumentType(res.doc_type)
        doc.type_confidence, doc.type_source = res.type_confidence, res.type_method
    if doc.date_source != "user":
        if res.exam_date:
            doc.exam_date, doc.date_source = res.exam_date, "detected"
        else:
            doc.exam_date, doc.date_source = doc.created_at.date(), "upload"
            warnings.append("Date d'examen introuvable dans le document : date de dépôt utilisée, à corriger.")
    elif res.exam_date and res.exam_date != doc.exam_date:
        warnings.append(f"La date lue dans le document ({res.exam_date:%d/%m/%Y}) diffère de la date saisie.")

    # Ré-extraction : on remplace les mesures encore non validées de ce document
    db.execute(delete(Measurement).where(Measurement.source_document_id == doc.id,
                                         Measurement.validation_status.in_([ValidationStatus.pending,
                                                                            ValidationStatus.suspect])))
    values = res.values if doc.type.value == res.doc_type else []
    if forced_type and forced_type.value != res.doc_type:
        warnings.append("Le type choisi diffère du type détecté : aucune valeur extraite automatiquement.")
    existing = db.scalars(select(Measurement).where(Measurement.patient_id == doc.patient_id,
                                                    Measurement.date == doc.exam_date)).all()
    duplicates = 0
    for v in values:
        if any(m.parameter_code == v.param and sorted(m.context or []) == sorted(v.context) and _same(m.value, v.value)
               for m in existing):
            duplicates += 1
            continue
        db.add(Measurement(patient_id=doc.patient_id, parameter_code=v.param, value=v.value, unit=v.unit,
                           date=doc.exam_date, context=v.context, source_document_id=doc.id,
                           source_text=v.source_text[:500], printed_value=v.printed_value,
                           printed_unit=v.printed_unit, flags=v.flags, bbox=v.bbox, confidence=v.confidence,
                           validation_status=ValidationStatus.suspect if v.suspect else ValidationStatus.pending))
    if duplicates:
        warnings.append(f"{duplicates} valeur(s) déjà présente(s) dans le dossier, non dupliquée(s).")
    if doc.type in (DocumentType.bilan_bio, DocumentType.efr, DocumentType.compte_rendu) and not values:
        warnings.append("Aucune valeur reconnue dans ce document.")
    doc.warnings = warnings
    # Ordonnances (phase 4) et radiographies (phase 5) n'ont pas de mesures biologiques à valider ici
    nothing_to_validate = not values and doc.type in (DocumentType.ordonnance, DocumentType.radiographie)
    doc.status = DocumentStatus.validated if nothing_to_validate else DocumentStatus.extracted
    db.commit()


def refresh_document_status(db: Session, doc: Document) -> None:
    """Un document est « validé » quand plus aucune de ses mesures n'attend de décision."""
    db.flush()  # sessions sans autoflush : rendre visibles les décisions en cours avant de compter
    pending = db.scalar(select(Measurement.id).where(
        Measurement.source_document_id == doc.id,
        Measurement.validation_status.in_([ValidationStatus.pending, ValidationStatus.suspect])).limit(1))
    if doc.status in (DocumentStatus.extracted, DocumentStatus.validated):
        doc.status = DocumentStatus.extracted if pending else DocumentStatus.validated
