"""Recherche sémantique dans le texte des documents validés (F-E4, volet RAG sans génération).

- Découpage : texte extrait (PDF natif ou OCR) d'un document validé, en passages de ~500 caractères (lignes entières).
- Plongements : intfloat/multilingual-e5-small (CPU, préfixes « passage: » / « query: »), moyenne des états cachés
  puis normalisation ; stockés en base avec le passage (table `document_chunks`), calculés au premier besoin.
- Recherche : similarité cosinus ; seuil 0,80 mesuré (passage pertinent ~0,85, question hors sujet < 0,75) et
  passages à moins de 0,03 du meilleur. Pas de base vectorielle séparée (T36) : quelques centaines de passages
  par patient, un produit matriciel suffit.
Le modèle est un composant optionnel : s'il manque, l'assistant répond sans le volet recherche.
"""
from __future__ import annotations

import logging
import uuid
from functools import lru_cache

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, DocumentStatus
from app.services.sheet import DOC_TYPES

log = logging.getLogger("medimind.search")
MODEL_NAME = "intfloat/multilingual-e5-small"
THRESHOLD = 0.80
MARGIN = 0.03
CHUNK_CHARS = 500


@lru_cache(maxsize=1)
def _model():
    import torch  # noqa: F401 - déjà présent (imagerie)
    from transformers import AutoModel, AutoTokenizer

    return AutoTokenizer.from_pretrained(MODEL_NAME), AutoModel.from_pretrained(MODEL_NAME).eval()


def embed(texts: list[str], kind: str) -> np.ndarray:
    """Vecteurs normalisés (n, 384). `kind` : « passage » ou « query » (convention e5)."""
    import torch

    tok, model = _model()
    batch = tok([f"{kind}: {t}" for t in texts], padding=True, truncation=True, max_length=256, return_tensors="pt")
    with torch.no_grad():
        hidden = model(**batch).last_hidden_state
    mask = batch["attention_mask"].unsqueeze(-1).float()
    vec = (hidden * mask).sum(1) / mask.sum(1)
    return torch.nn.functional.normalize(vec, dim=1).numpy()


def available() -> bool:
    try:
        _model()
        return True
    except Exception as exc:  # noqa: BLE001 - recherche optionnelle
        log.warning(f"Modèle de recherche indisponible : {type(exc).__name__}")
        return False


def chunk(text: str) -> list[str]:
    out, cur = [], ""
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if cur and len(cur) + len(line) > CHUNK_CHARS:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def ensure_index(db: Session, patient_id: uuid.UUID) -> None:
    """Indexe les documents validés qui ne le sont pas encore."""
    indexed = set(db.scalars(select(DocumentChunk.document_id).where(DocumentChunk.patient_id == patient_id)))
    docs = [d for d in db.scalars(select(Document).where(Document.patient_id == patient_id,
                                                        Document.status == DocumentStatus.validated))
            if d.id not in indexed and d.extracted_text]
    for d in docs:
        parts = chunk(d.extracted_text)
        if not parts:
            continue
        for i, (text, vec) in enumerate(zip(parts, embed(parts, "passage"), strict=True)):
            db.add(DocumentChunk(patient_id=patient_id, document_id=d.id, idx=i, text=text,
                                 embedding=[round(float(x), 5) for x in vec], model=MODEL_NAME))
    if docs:
        db.commit()


def search(db: Session, patient_id: uuid.UUID, question: str, k: int = 3) -> list[dict]:
    ensure_index(db, patient_id)
    rows = db.execute(select(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id)
                      .where(DocumentChunk.patient_id == patient_id,
                             Document.status == DocumentStatus.validated)).all()
    if not rows:
        return []
    matrix = np.array([c.embedding for c, _ in rows], dtype=np.float32)
    scores = matrix @ embed([question], "query")[0]
    best = float(scores.max())
    if best < THRESHOLD:
        return []
    order = [i for i in np.argsort(-scores)[:k] if scores[i] >= max(THRESHOLD, best - MARGIN)]
    return [{"document_id": str(rows[i][1].id), "text": rows[i][0].text, "score": round(float(scores[i]), 3),
             "type": DOC_TYPES.get(rows[i][1].type.value, "Document"), "date": rows[i][1].exam_date}
            for i in order]
