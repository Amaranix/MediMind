"""Stockage des fichiers déposés sur le volume (storage/<patient>/<document>.<ext>).

Le type réel est déterminé par la signature binaire du fichier, jamais par son nom ni par l'en-tête envoyé
par le navigateur. Les noms de fichiers sur disque sont générés côté serveur.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from app.core.config import get_settings

SIGNATURES = {
    b"%PDF-": ("application/pdf", "pdf"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
    b"\xff\xd8\xff": ("image/jpeg", "jpg"),
}


def sniff(data: bytes) -> tuple[str, str] | None:
    """Renvoie (type MIME, extension) d'après la signature, ou None si le format n'est pas accepté."""
    for magic, kind in SIGNATURES.items():
        if data.startswith(magic):
            return kind
    return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def root() -> Path:
    return get_settings().storage_path


def save(patient_id: uuid.UUID, document_id: uuid.UUID, ext: str, data: bytes) -> str:
    """Écrit le fichier et renvoie son chemin relatif au stockage."""
    rel = Path(str(patient_id)) / f"{document_id}.{ext}"
    path = root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel.as_posix()


def absolute(rel: str) -> Path:
    path = (root() / rel).resolve()
    if root().resolve() not in path.parents:
        raise ValueError("chemin hors du stockage")
    return path


def page_cache(rel: str, page: int, width: int) -> Path:
    return absolute(rel).with_name(f"{Path(rel).stem}.p{page}.w{width}.png")
