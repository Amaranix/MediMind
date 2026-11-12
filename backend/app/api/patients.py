"""Patients du médecin connecté (F-A2). Toute lecture ou modification est journalisée."""
from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_patient_for_doctor, require_doctor
from app.db.models import Document, Job, Patient, User
from app.db.session import get_db
from app.schemas import PatientCreate, PatientOut, PatientUpdate
from app.services import alerts as alert_engine
from app.services import storage
from app.services.audit import audit
from app.services.referential import get_referential

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[PatientOut])
def list_patients(user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> list[PatientOut]:
    rows = db.scalars(select(Patient).where(Patient.doctor_id == user.id)
                      .order_by(Patient.last_name, Patient.first_name))
    return [PatientOut.from_row(p) for p in rows]


@router.post("", response_model=PatientOut, status_code=status.HTTP_201_CREATED)
def create_patient(body: PatientCreate, user: User = Depends(require_doctor),
                   db: Session = Depends(get_db)) -> PatientOut:
    patient = Patient(doctor_id=user.id, **body.model_dump())
    db.add(patient)
    db.commit()
    audit(db, user.id, "patient_create", "patient", patient.id)
    return PatientOut.from_row(patient)


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient: Patient = Depends(get_patient_for_doctor), user: User = Depends(require_doctor),
                db: Session = Depends(get_db)) -> PatientOut:
    audit(db, user.id, "patient_read", "patient", patient.id)
    return PatientOut.from_row(patient)


@router.patch("/{patient_id}", response_model=PatientOut)
def update_patient(body: PatientUpdate, patient: Patient = Depends(get_patient_for_doctor),
                   user: User = Depends(require_doctor), db: Session = Depends(get_db)) -> PatientOut:
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(patient, k, v)
    if "conditions" in changes:  # une règle réservée à une pathologie peut s'activer ou disparaître
        alert_engine.recompute(db, get_referential(), patient.id)
    db.commit()
    audit(db, user.id, "patient_update", "patient", patient.id, {"fields": sorted(changes)})
    return PatientOut.from_row(patient)


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_patient(patient: Patient = Depends(get_patient_for_doctor), user: User = Depends(require_doctor),
                   db: Session = Depends(get_db)) -> Response:
    """Suppression définitive : base (cascade : documents, mesures, traitements, événements, alertes, imagerie,
    fiches, conversations, passages indexés), fichiers du patient, tâches liées. L'audit garde la trace."""
    doc_ids = [str(i) for i in db.scalars(select(Document.id).where(Document.patient_id == patient.id))]
    n_docs = len(doc_ids)
    pid = patient.id
    if doc_ids:
        db.execute(delete(Job).where(Job.ref_id.in_(doc_ids)))
    db.delete(patient)
    db.commit()
    folder = storage.root() / str(pid)
    if folder.exists():
        shutil.rmtree(folder)
    audit(db, user.id, "patient_delete", "patient", pid, {"documents": n_docs})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
