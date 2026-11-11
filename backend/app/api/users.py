"""Gestion des comptes par l'administrateur (US17). Pas d'inscription publique."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.security import hash_password
from app.db.models import User
from app.db.session import get_db
from app.schemas import UserCreate, UserOut, UserUpdate
from app.services.audit import audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> User:
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un compte existe déjà avec cette adresse e-mail.")
    user = User(name=body.name, email=email, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    audit(db, admin.id, "user_create", "user", user.id, {"role": user.role.value})
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UserUpdate, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable.")
    if user.id == admin.id and body.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Vous ne pouvez pas désactiver votre propre compte.")
    if body.name is not None:
        user.name = body.name
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    db.commit()
    audit(db, admin.id, "user_update", "user", user.id,
          {"fields": [k for k, v in body.model_dump().items() if v is not None and k != "password"]
           + (["password"] if body.password else [])})
    return user
