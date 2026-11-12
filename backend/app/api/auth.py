"""Connexion, rafraîchissement de session et déconnexion.

Le jeton d'accès (15 min) est renvoyé dans le corps et gardé en mémoire par le frontend. Le jeton de
rafraîchissement (7 j) est posé dans un cookie httpOnly limité au chemin /api/auth, inaccessible au JavaScript.
"""
from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core import ratelimit
from app.core.config import get_settings
from app.core.security import create_token, decode_token, verify_password
from app.db.models import User
from app.db.session import get_db
from app.schemas import LoginIn, TokenOut, UserOut
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "medimind_refresh"


def _issue(response: Response, user: User) -> TokenOut:
    s = get_settings()
    response.set_cookie(REFRESH_COOKIE, create_token(user.id, user.role.value, "refresh"),
                        max_age=s.refresh_token_days * 86400, httponly=True, secure=s.cookie_secure,
                        samesite="strict", path="/api/auth")
    return TokenOut(access_token=create_token(user.id, user.role.value, "access"),
                    expires_in=s.access_token_minutes * 60)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    keys = (f"email:{email}", f"ip:{request.client.host if request.client else '?'}")
    if wait := ratelimit.retry_after(*keys):
        audit(db, None, "login_blocked", "user", details={"email": email})
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Trop de tentatives de connexion. Réessayez dans {wait // 60 + 1} minute(s).",
                            headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        ratelimit.failed(*keys)
        audit(db, user.id if user else None, "login_failed", "user", details={"email": email})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Adresse e-mail ou mot de passe incorrect.")
    ratelimit.succeeded(keys[0])
    audit(db, user.id, "login", "user", user.id)
    return _issue(response, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(response: Response, db: Session = Depends(get_db),
            medimind_refresh: str | None = Cookie(default=None)) -> TokenOut:
    try:
        payload = decode_token(medimind_refresh or "", "refresh")
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expirée, reconnectez-vous.")
    return _issue(response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> Response:
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
