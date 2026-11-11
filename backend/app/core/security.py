"""Mots de passe (bcrypt) et jetons JWT (accès court, rafraîchissement long)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import bcrypt
import jwt

from app.core.config import get_settings

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(user_id: uuid.UUID, role: str, token_type: TokenType) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    is_access = token_type == "access"  # noqa: S105 - type de jeton, pas un secret
    ttl = timedelta(minutes=s.access_token_minutes) if is_access else timedelta(days=s.refresh_token_days)
    payload = {"sub": str(user_id), "role": role, "type": token_type, "iat": now, "exp": now + ttl,
               "jti": uuid.uuid4().hex}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType) -> dict:
    """Lève jwt.InvalidTokenError si le jeton est invalide, expiré ou du mauvais type."""
    s = get_settings()
    payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], options={"require": ["exp", "sub"]})
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload
