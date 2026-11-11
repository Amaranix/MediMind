"""Journal d'audit (F-A9) : qui a fait quoi, sur quel objet, quand."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import AuditLog


def audit(db: Session, user_id: uuid.UUID | None, action: str, object_type: str | None = None,
          object_id: uuid.UUID | str | None = None, details: dict | None = None, *, commit: bool = True) -> None:
    db.add(AuditLog(user_id=user_id, action=action, object_type=object_type,
                    object_id=str(object_id) if object_id else None, details=details))
    if commit:
        db.commit()
