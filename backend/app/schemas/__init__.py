"""Schémas Pydantic d'entrée et de sortie de l'API."""
from __future__ import annotations

import datetime as dt
import re
import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.db.models import JobStatus, Role, Sex

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _email(v: str) -> str:
    """Identifiant de connexion au format e-mail. Les domaines internes (.local) sont acceptés :
    aucun message n'est jamais envoyé à ces adresses."""
    v = v.strip().lower()
    if len(v) > 255 or not _EMAIL_RE.match(v):
        raise ValueError("Adresse e-mail invalide.")
    return v


Email = Annotated[str, AfterValidator(_email)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- authentification et comptes
class LoginIn(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - type de jeton OAuth2, pas un secret
    expires_in: int


class UserOut(ORM):
    id: uuid.UUID
    name: str
    email: Email
    role: Role
    is_active: bool


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: Email
    password: str = Field(min_length=10, max_length=128)
    role: Role = Role.doctor


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


# ---------------------------------------------------------------- patients
def age_on(birth: dt.date, today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


class PatientBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    birth_date: dt.date
    sex: Sex
    height_cm: int | None = Field(default=None, ge=120, le=230)
    antecedents: str | None = Field(default=None, max_length=4000)
    pack_years: float | None = Field(default=None, ge=0, le=300)
    allergies: str | None = Field(default=None, max_length=2000)
    base_treatments: str | None = Field(default=None, max_length=2000)

    @field_validator("birth_date")
    @classmethod
    def adult_only(cls, v: dt.date) -> dt.date:
        if v > dt.date.today():
            raise ValueError("La date de naissance est dans le futur.")
        if age_on(v) < 18:
            raise ValueError("MediMind est réservé aux patients adultes (18 ans ou plus).")
        if age_on(v) > 120:
            raise ValueError("Date de naissance invraisemblable.")
        return v


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    height_cm: int | None = Field(default=None, ge=120, le=230)
    antecedents: str | None = Field(default=None, max_length=4000)
    pack_years: float | None = Field(default=None, ge=0, le=300)
    allergies: str | None = Field(default=None, max_length=2000)
    base_treatments: str | None = Field(default=None, max_length=2000)


class PatientOut(PatientBase, ORM):
    id: uuid.UUID
    age: int

    @classmethod
    def from_row(cls, p) -> PatientOut:
        data = {c: getattr(p, c) for c in PatientBase.model_fields}
        return cls.model_construct(id=p.id, age=age_on(p.birth_date), **data)


# ---------------------------------------------------------------- jobs, audit, santé
class JobOut(ORM):
    id: uuid.UUID
    type: str
    ref_id: str | None
    status: JobStatus
    attempts: int
    error: str | None
    created_at: dt.datetime
    finished_at: dt.datetime | None


class AuditOut(ORM):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    object_type: str | None
    object_id: str | None
    timestamp: dt.datetime


class HealthOut(BaseModel):
    status: str
    database: str
    ollama: str
    ollama_model: str
    imaging_model: str
    referential_version: str


# ---------------------------------------------------------------- documents et mesures
class UploadResult(BaseModel):
    filename: str
    status: str  # queued | duplicate | rejected
    message: str | None = None
    document_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None


class DocumentOut(ORM):
    id: uuid.UUID
    patient_id: uuid.UUID
    type: str
    type_confidence: float | None
    type_source: str | None
    exam_date: dt.date | None
    date_source: str | None
    original_name: str
    mime_type: str
    status: str
    confidence: float | None
    page_count: int | None
    warnings: list[str] | None
    processing_seconds: float | None
    created_at: dt.datetime
    pending_count: int = 0
    validated_count: int = 0


class DocumentUpdate(BaseModel):
    type: str | None = None
    exam_date: dt.date | None = None


class MeasurementOut(ORM):
    id: uuid.UUID
    parameter_code: str
    value: float
    unit: str
    date: dt.date
    context: list[str]
    source_document_id: uuid.UUID | None
    source_text: str | None
    printed_value: float | None
    printed_unit: str | None
    flags: list[str]
    bbox: dict | None
    confidence: float | None
    validation_status: str
    validated_at: dt.datetime | None


class MeasurementAction(BaseModel):
    action: str = Field(pattern="^(validate|correct|reject|reset)$")
    value: float | None = None
    context: list[str] | None = None
