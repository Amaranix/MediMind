"""Limitation des tentatives de connexion : après MAX_FAILURES échecs en WINDOW pour un même compte ou une même
adresse IP, nouvelles tentatives refusées (429) jusqu'à la fin de la fenêtre. Un succès efface le compteur du compte.

shortcut: compteur en mémoire d'un seul processus (uvicorn mono-processus du démonstrateur) ; à remplacer par un
stockage partagé (base ou Redis) si le backend tourne un jour sur plusieurs processus.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

MAX_FAILURES = 5
WINDOW = 15 * 60  # secondes

_failures: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _prune(key: str, now: float) -> deque[float]:
    q = _failures[key]
    while q and now - q[0] > WINDOW:
        q.popleft()
    return q


def retry_after(*keys: str) -> int:
    """Secondes à attendre si l'une des clés est bloquée, sinon 0."""
    now = time.monotonic()
    with _lock:
        waits = [int(WINDOW - (now - q[0])) + 1 for k in keys if len(q := _prune(k, now)) >= MAX_FAILURES]
    return max(waits, default=0)


def failed(*keys: str) -> None:
    now = time.monotonic()
    with _lock:
        for k in keys:
            _prune(k, now).append(now)


def succeeded(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def reset() -> None:
    with _lock:
        _failures.clear()
