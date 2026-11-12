"""Modèle de données (docs/PLAN.md §7.3, docs/uml/class-diagram.puml).

Isolation : toute donnée clinique est rattachée à un patient, lui-même rattaché à un médecin (`doctor_id`).
Les types JSON deviennent JSONB sous PostgreSQL.
"""
from __future__ import annotations

import datetime as dt
import enum
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(DeclarativeBase):
    pass


def _enum(cls: type[enum.Enum], name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e], native_enum=False, length=32)


class Role(str, enum.Enum):
    doctor = "doctor"
    admin = "admin"


class Sex(str, enum.Enum):
    M = "M"
    F = "F"


class DocumentType(str, enum.Enum):
    bilan_bio = "bilan_bio"
    efr = "efr"
    compte_rendu = "compte_rendu"
    ordonnance = "ordonnance"
    radiographie = "radiographie"
    inconnu = "inconnu"


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    extracted = "extracted"
    validated = "validated"
    failed = "failed"


class ValidationStatus(str, enum.Enum):
    pending = "pending"
    validated = "validated"
    corrected = "corrected"
    rejected = "rejected"
    suspect = "suspect"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class AlertState(str, enum.Enum):
    open = "open"
    acknowledged = "acknowledged"


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(_enum(Role, "role"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Patient(Base):
    __tablename__ = "patients"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(80))
    birth_date: Mapped[dt.date] = mapped_column(Date)
    sex: Mapped[Sex] = mapped_column(_enum(Sex, "sex"))
    height_cm: Mapped[int | None] = mapped_column(Integer)
    antecedents: Mapped[str | None] = mapped_column(Text)
    pack_years: Mapped[float | None] = mapped_column(Float)
    allergies: Mapped[str | None] = mapped_column(Text)
    base_treatments: Mapped[str | None] = mapped_column(Text)
    conditions: Mapped[list] = mapped_column(JsonType, default=list)  # pathologies suivies (référentiel)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    documents: Mapped[list[Document]] = relationship(back_populates="patient", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    type: Mapped[DocumentType] = mapped_column(_enum(DocumentType, "document_type"), default=DocumentType.inconnu)
    exam_date: Mapped[dt.date | None] = mapped_column(Date)
    original_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    ocr_boxes: Mapped[dict | None] = mapped_column(JsonType)
    status: Mapped[DocumentStatus] = mapped_column(_enum(DocumentStatus, "document_status"),
                                                  default=DocumentStatus.uploaded)
    confidence: Mapped[float | None] = mapped_column(Float)
    type_confidence: Mapped[float | None] = mapped_column(Float)
    type_source: Mapped[str | None] = mapped_column(String(16))   # user | rules | llm | image
    date_source: Mapped[str | None] = mapped_column(String(16))   # user | detected | upload
    page_count: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[list | None] = mapped_column(JsonType)
    processing_seconds: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    patient: Mapped[Patient] = relationship(back_populates="documents")


class Parameter(Base):
    """Copie du référentiel clinique (synchronisée au démarrage depuis le YAML)."""
    __tablename__ = "parameters"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(32))
    synonyms: Mapped[list] = mapped_column(JsonType, default=list)
    unit: Mapped[str] = mapped_column(String(32))
    alt_units: Mapped[dict] = mapped_column(JsonType, default=dict)
    plausible_min: Mapped[float | None] = mapped_column(Float)
    plausible_max: Mapped[float | None] = mapped_column(Float)
    ref_low: Mapped[float | None] = mapped_column(Float)
    ref_high: Mapped[float | None] = mapped_column(Float)


class Measurement(Base):
    __tablename__ = "measurements"
    __table_args__ = (Index("ix_measurements_patient_param_date", "patient_id", "parameter_code", "date"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    parameter_code: Mapped[str] = mapped_column(ForeignKey("parameters.code"))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    date: Mapped[dt.date] = mapped_column(Date)
    context: Mapped[list] = mapped_column(JsonType, default=list)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    source_text: Mapped[str | None] = mapped_column(Text)
    printed_value: Mapped[float | None] = mapped_column(Float)
    printed_unit: Mapped[str | None] = mapped_column(String(32))
    flags: Mapped[list] = mapped_column(JsonType, default=list)
    bbox: Mapped[dict | None] = mapped_column(JsonType)
    confidence: Mapped[float | None] = mapped_column(Float)
    validation_status: Mapped[ValidationStatus] = mapped_column(_enum(ValidationStatus, "validation_status"),
                                                                default=ValidationStatus.pending)
    validated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Treatment(Base):
    __tablename__ = "treatments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    molecule: Mapped[str] = mapped_column(String(120))
    drug_class: Mapped[str | None] = mapped_column(String(40))
    dosage: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    validation_status: Mapped[ValidationStatus] = mapped_column(_enum(ValidationStatus, "validation_status"),
                                                                default=ValidationStatus.pending)
    duration_days: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[float | None] = mapped_column(Float)
    bbox: Mapped[dict | None] = mapped_column(JsonType)
    source_text: Mapped[str | None] = mapped_column(Text)
    flags: Mapped[list | None] = mapped_column(JsonType)
    validated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ClinicalEvent(Base):
    __tablename__ = "clinical_events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    date: Mapped[dt.date] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"))
    validation_status: Mapped[ValidationStatus] = mapped_column(_enum(ValidationStatus, "validation_status"),
                                                                default=ValidationStatus.pending)
    confidence: Mapped[float | None] = mapped_column(Float)
    bbox: Mapped[dict | None] = mapped_column(JsonType)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    validated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    validated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class Imaging(Base):
    __tablename__ = "imaging"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), unique=True)
    date: Mapped[dt.date] = mapped_column(Date)
    view: Mapped[str | None] = mapped_column(String(8))
    quality_flag: Mapped[str | None] = mapped_column(String(40))
    scores: Mapped[dict | None] = mapped_column(JsonType)
    uncertainty: Mapped[dict | None] = mapped_column(JsonType)
    gradcam_path: Mapped[str | None] = mapped_column(String(512))
    model_name: Mapped[str | None] = mapped_column(String(80))
    model_version: Mapped[str | None] = mapped_column(String(40))
    doctor_assessment: Mapped[str | None] = mapped_column(Text)
    # F-C7 : annotations du médecin, coordonnées normalisées 0..1 ({type: arrow|text, x1, y1, x2, y2, text})
    annotations: Mapped[list] = mapped_column(JsonType, default=list)


class RadiographComparison(Base):
    """F-C6 : qualification par le médecin de l'évolution entre deux radiographies (l'IA n'en produit aucune, D5)."""
    __tablename__ = "radiograph_comparisons"
    __table_args__ = (UniqueConstraint("document_a_id", "document_b_id"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    document_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    document_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    qualification: Mapped[str] = mapped_column(String(20))  # amelioration | stable | aggravation | non_evaluable
    comment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(String(40))
    ruleset_version: Mapped[str] = mapped_column(String(20))
    source_values: Mapped[dict] = mapped_column(JsonType)
    date: Mapped[dt.date] = mapped_column(Date)
    state: Mapped[AlertState] = mapped_column(_enum(AlertState, "alert_state"), default=AlertState.open)
    current: Mapped[bool] = mapped_column(Boolean, default=True)  # porte sur la donnée la plus récente
    message: Mapped[str | None] = mapped_column(Text)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class ConsultationSheet(Base):
    __tablename__ = "consultation_sheets"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    facts: Mapped[dict] = mapped_column(JsonType)
    text: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(16))
    verification: Mapped[dict] = mapped_column(JsonType)
    pdf_path: Mapped[str | None] = mapped_column(String(512))


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), index=True)
    messages: Mapped[list] = mapped_column(JsonType, default=list)
    cited_sources: Mapped[list] = mapped_column(JsonType, default=list)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(60))
    object_type: Mapped[str | None] = mapped_column(String(40))
    object_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JsonType)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(40))
    ref_id: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[JobStatus] = mapped_column(_enum(JobStatus, "job_status"), default=JobStatus.queued)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
