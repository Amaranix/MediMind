"""Patients du médecin connecté (F-A2). Toute lecture ou modification est journalisée."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_patient_for_doctor, require_doctor
from app.db.models import Patient, User
from app.db.session import get_db
from app.schemas import PatientCreate, PatientOut, PatientUpdate
from app.services.audit import audit

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
    db.commit()
    audit(db, user.id, "patient_update", "patient", patient.id, {"fields": sorted(changes)})
    return PatientOut.from_row(patient)
