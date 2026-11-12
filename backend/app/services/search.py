"""Recherche sémantique dans le texte des documents validés (F-E4, volet RAG sans génération).

- Découpage : texte extrait (PDF natif ou OCR) d'un document validé, sans les lignes répétées d'un document à
  l'autre (en-tête du cabinet, signature, pied de page : présentes dans au moins 3 documents du patient) ni les
  lignes d'identité et de date ; passages de ~300 caractères (lignes entières). Sans ce nettoyage, l'en-tête
  dominait la similarité (mesuré sur A01 : une question hors sujet obtenait 0,81).
- Plongements : intfloat/multilingual-e5-small (CPU, préfixes « passage: » / « query: »), moyenne des états cachés
  puis normalisation ; stockés en base avec le passage (table `document_chunks`), calculés au premier besoin.
- Recherche : similarité cosinus ; seuil 0,83 mesuré sur A01 (pertinent 0,84 à 0,88, hors sujet ≤ 0,82) et
  passages à moins de 0,03 du meilleur. Pas de base vectorielle séparée (T36) : quelques centaines de passages
  par patient, un produit matriciel suffit.
Le modèle est un composant optionnel : s'il manque, l'assistant répond sans le volet recherche.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections import Counter
from functools import lru_cache

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, DocumentStatus, DocumentType
from app.services.sheet import DOC_TYPES

log = logging.getLogger("medimind.search")
MODEL_NAME = "intfloat/multilingual-e5-small"
INDEX_TAG = f"{MODEL_NAME}|v3"  # changer la version reconstruit l'index (découpage modifié)
THRESHOLD = 0.83  # A01 : passages pertinents 0,84 à 0,88 ; question hors sujet 0,82 au plus (marge étroite)
MARGIN = 0.03
CHUNK_CHARS = 300
BOILERPLATE_MIN_DOCS = 3
IDENTITY = re.compile(r"^(le \d{1,2}/\d{1,2}/\d{4}|patient\s*:|n[ée]\(?e?\)? le|date|dr\b)", re.I)


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


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def chunk(text: str, boilerplate: frozenset[str] = frozenset()) -> list[str]:
    out, cur = [], ""
    for line in _lines(text):
        if line.lower() in boilerplate or IDENTITY.match(line):
            continue
        if cur and len(cur) + len(line) > CHUNK_CHARS:
            out.append(cur)
            cur = ""
        cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return [c for c in out if sum(ch.isalpha() for ch in c) >= 0.5 * len(c)]  # écarte les débris d'OCR


def ensure_index(db: Session, patient_id: uuid.UUID) -> None:
    """Indexe les documents validés qui ne le sont pas encore (et reconstruit un index d'une version antérieure)."""
    old = db.scalars(select(DocumentChunk).where(DocumentChunk.patient_id == patient_id,
                                                 DocumentChunk.model != INDEX_TAG)).all()
    for c in old:
        db.delete(c)
    db.flush()
    validated = [d for d in db.scalars(select(Document).where(Document.patient_id == patient_id,
                                                             Document.status == DocumentStatus.validated))
                 if d.extracted_text and d.type != DocumentType.radiographie]  # l'OCR d'une radio n'est que du bruit
    counts = Counter(line.lower() for d in validated for line in set(_lines(d.extracted_text)))
    boilerplate = frozenset(line for line, n in counts.items() if n >= BOILERPLATE_MIN_DOCS)
    indexed = set(db.scalars(select(DocumentChunk.document_id).where(DocumentChunk.patient_id == patient_id)))
    todo = [d for d in validated if d.id not in indexed]
    for d in todo:
        parts = chunk(d.extracted_text, boilerplate)
        if not parts:
            continue
        for i, (text, vec) in enumerate(zip(parts, embed(parts, "passage"), strict=True)):
            db.add(DocumentChunk(patient_id=patient_id, document_id=d.id, idx=i, text=text,
                                 embedding=[round(float(x), 5) for x in vec], model=INDEX_TAG))
    if todo or old:
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
