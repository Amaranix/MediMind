"""Tâche de fond `ingest_document` : exécute le pipeline et écrit les mesures « à valider » en base.

Règles :
- la date d'examen saisie par le médecin prime sur la date détectée ; à défaut, date de dépôt + avertissement ;
- le type choisi par le médecin prime sur la classification automatique ;
- une mesure identique déjà présente (paramètre, date, contexte, valeur) n'est pas recréée (dédoublonnage) ;
- une valeur hors bornes plausibles est créée avec le statut `suspect`.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    ClinicalEvent,
    Document,
    DocumentStatus,
    DocumentType,
    Job,
    Measurement,
    Treatment,
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

    # Traitements (ordonnances) et événements (comptes rendus), eux aussi « à valider »
    open_ = [ValidationStatus.pending, ValidationStatus.suspect]
    db.execute(delete(Treatment).where(Treatment.source_document_id == doc.id,
                                       Treatment.validation_status.in_(open_)))
    db.execute(delete(ClinicalEvent).where(ClinicalEvent.source_document_id == doc.id,
                                           ClinicalEvent.validation_status.in_(open_)))
    if doc.type.value == res.doc_type:
        for t in res.treatments:
            end = doc.exam_date + dt.timedelta(days=t.duration_days) if t.duration_days else None
            db.add(Treatment(patient_id=doc.patient_id, molecule=t.molecule, drug_class=t.drug_class,
                             dosage=t.dosage, start_date=doc.exam_date, end_date=end, duration_days=t.duration_days,
                             source_document_id=doc.id, confidence=t.confidence, bbox=t.bbox,
                             source_text=t.source_text, flags=t.flags))
        for e in res.events:
            db.add(ClinicalEvent(patient_id=doc.patient_id, type=e.type, date=e.date or doc.exam_date,
                                 end_date=e.end_date, note=e.note, source_document_id=doc.id,
                                 confidence=e.confidence, bbox=e.bbox))
    if doc.type in (DocumentType.bilan_bio, DocumentType.efr, DocumentType.compte_rendu) and not values:
        warnings.append("Aucune valeur reconnue dans ce document.")
    doc.warnings = warnings
    if doc.type == DocumentType.radiographie:
        try:
            from app.services.imaging import run_analysis
            run_analysis(db, doc)
        except Exception as exc:  # noqa: BLE001 - l'analyse IA ne doit jamais bloquer le dépôt
            warnings.append(f"Analyse IA de la radiographie indisponible ({type(exc).__name__}).")
        doc.warnings = warnings
    doc.status = DocumentStatus.extracted
    db.flush()
    refresh_document_status(db, doc)
    db.commit()


def refresh_document_status(db: Session, doc: Document) -> None:
    """Un document est « validé » quand plus aucune de ses mesures n'attend de décision."""
    db.flush()  # sessions sans autoflush : rendre visibles les décisions en cours avant de compter
    # - des éléments attendent une décision                -> « à valider »
    # - tout est décidé                                      -> « validé »
    # - rien n'a été extrait : radiographie (analysée par le module imagerie) -> « validé » ;
    #   autre type -> reste « à valider » pour que le médecin vérifie le type ou le document
    if doc.status not in (DocumentStatus.extracted, DocumentStatus.validated):
        return
    open_ = [ValidationStatus.pending, ValidationStatus.suspect]
    models = (Measurement, Treatment, ClinicalEvent)
    pending = any(db.scalar(select(m.id).where(m.source_document_id == doc.id, m.validation_status.in_(open_))
                            .limit(1)) for m in models)
    extracted = any(db.scalar(select(m.id).where(m.source_document_id == doc.id).limit(1)) for m in models)
    if pending:
        doc.status = DocumentStatus.extracted
    elif extracted or doc.type == DocumentType.radiographie:
        doc.status = DocumentStatus.validated
    else:
        doc.status = DocumentStatus.extracted
