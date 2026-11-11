"""Dépendances d'accès : utilisateur courant, rôle, et isolation médecin/patient.

Règle d'isolation : un médecin n'accède qu'à ses propres patients ; un patient d'un autre médecin renvoie
404 (on ne révèle pas son existence). L'administrateur n'a accès à aucune donnée patient.
"""
from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.models import Patient, Role, User
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentification requise.",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_token(creds.credentials, "access")
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée.",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def require_role(*roles: Role):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Action non autorisée pour ce rôle.")
        return user
    return dep


require_doctor = require_role(Role.doctor)
require_admin = require_role(Role.admin)


def get_patient_for_doctor(patient_id: uuid.UUID, user: User = Depends(require_doctor),
                           db: Session = Depends(get_db)) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None or patient.doctor_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient introuvable.")
    return patient
