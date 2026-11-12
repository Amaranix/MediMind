"""Client unique vers le LLM local (Ollama). Aucun autre chemin réseau sortant n'est autorisé (D3).

Sorties contraintes par schéma JSON (paramètre `format` d'Ollama). Toute erreur renvoie None : l'appelant
retombe sur les règles ou laisse la décision au médecin.
"""
from __future__ import annotations

import json
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger("medimind.llm")


def generate_json(prompt: str, schema: dict, system: str) -> dict | None:
    s = get_settings()
    if not s.llm_enabled:
        return None
    try:
        r = httpx.post(f"{s.ollama_url}/api/chat", timeout=s.llm_timeout_s, json={
            "model": s.ollama_model, "stream": False, "format": schema,
            "options": {"temperature": 0, "num_ctx": 4096},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        })
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])
    except Exception as exc:  # noqa: BLE001 - le LLM est un repli, jamais bloquant
        log.warning(f"LLM indisponible ou réponse invalide : {type(exc).__name__}")
        return None


def generate_text(prompt: str, system: str, max_tokens: int = 300) -> str | None:
    """Texte libre (sans format JSON imposé : avec un petit modèle, la grammaire JSON peut boucler sans fin)."""
    s = get_settings()
    if not s.llm_enabled:
        return None
    try:
        # 20 à 75 s mesurés par essai sur le poste cible (CPU) : délai propre, plus long que la classification
        r = httpx.post(f"{s.ollama_url}/api/chat", timeout=max(s.llm_timeout_s, 90.0), json={
            "model": s.ollama_model, "stream": False,
            "options": {"temperature": 0, "num_ctx": 4096, "num_predict": max_tokens},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        })
        r.raise_for_status()
        return r.json()["message"]["content"].strip() or None
    except Exception as exc:  # noqa: BLE001 - la rédaction assistée est optionnelle, jamais bloquante
        log.warning(f"LLM indisponible : {type(exc).__name__}")
        return None


def model_name() -> str:
    return get_settings().ollama_model


DOC_TYPES = ["bilan_bio", "efr", "compte_rendu", "ordonnance", "inconnu"]


def classify_document(text: str) -> tuple[str, float] | None:
    schema = {"type": "object", "properties": {"type": {"type": "string", "enum": DOC_TYPES},
                                               "confidence": {"type": "number"}},
              "required": ["type", "confidence"]}
    system = ("Tu classes un document médical en : bilan_bio (analyses de laboratoire), efr (explorations "
              "fonctionnelles respiratoires), compte_rendu (consultation ou hospitalisation), ordonnance, ou "
              "inconnu. Réponds uniquement en JSON.")
    out = generate_json(text[:3000], schema, system)
    if not out or out.get("type") not in DOC_TYPES:
        return None
    return out["type"], max(0.0, min(1.0, float(out.get("confidence", 0.5))))


def extract_values(text: str, allowed: list[str]) -> list[dict]:
    """Extraction de secours sur texte libre. Le résultat est filtré par l'appelant : toute valeur absente
    littéralement du texte source est rejetée."""
    schema = {"type": "object", "properties": {"values": {"type": "array", "items": {
        "type": "object", "properties": {"param": {"type": "string", "enum": allowed},
                                         "value": {"type": "string"}, "unit": {"type": "string"}},
        "required": ["param", "value", "unit"]}}}, "required": ["values"]}
    system = ("Extrais uniquement les valeurs explicitement écrites dans le texte, recopiées exactement. "
              "N'invente jamais de valeur, d'unité ni de date. Si une valeur est absente, omets-la.")
    out = generate_json(text[:4000], schema, system)
    return out.get("values", []) if out else []
