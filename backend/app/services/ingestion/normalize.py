"""Normalisation (F-A7) : libellés -> code du référentiel, unités -> unité canonique, plausibilité.

Les fonctions sont pures (sans base de données) et testées unitairement.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from app.services.referential import ParameterDef, Referential

# Libellés complémentaires rencontrés sur les comptes rendus de laboratoire (en plus des synonymes du YAML)
EXTRA_LABELS = {
    "WBC": ["leucocytes totaux", "globules blancs", "gb", "leucocytes"],
    "NEUT": ["poly neutrophiles", "polynucleaires neutrophiles", "neutrophiles", "pnn"],
    "LYMPH": ["lymphocytes"],
    "EOS": ["poly eosinophiles", "polynucleaires eosinophiles", "eosinophiles", "pne"],
    "HB": ["hemoglobine", "hb", "hgb"],
    "PLT": ["numeration plaquettaire", "plaquettes", "plt"],
    "CRP": ["proteine c reactive", "c reactive proteine", "crp"],
    "PCT": ["procalcitonine", "pct"],
    "CREAT": ["creatinine serique", "creatininemie", "creatinine"],
}


def fold(text: str) -> str:
    """Minuscules, sans accents, ponctuation -> espace."""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9%/]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class LabelMatch:
    code: str
    n_words: int   # nombre de mots du libellé consommés en début de ligne
    score: float   # 100 = exact


class LabelMatcher:
    def __init__(self, ref: Referential, codes: set[str] | None = None):
        self.labels: list[tuple[str, str]] = []
        for p in ref.parameters:
            if codes and p.code not in codes:
                continue
            for s in [p.name, *p.synonyms, *EXTRA_LABELS.get(p.code, [])]:
                f = fold(s)
                if f:
                    self.labels.append((f, p.code))
        self.labels = sorted(set(self.labels), key=lambda x: -len(x[0]))  # le plus long d'abord

    def match_prefix(self, words: list[str], min_score: float = 88) -> LabelMatch | None:
        """Cherche un libellé connu au début de la ligne. Les mots du DOCUMENT sont ajoutés un à un
        (un mot comme « C-réactive » donne deux mots une fois plié) ; le libellé exact le plus long gagne,
        sinon la meilleure correspondance approchée (erreurs d'OCR) de longueur voisine."""
        exact: dict[str, str] = {}
        for label, code in self.labels:
            exact.setdefault(label, code)
        best_exact: LabelMatch | None = None
        best_fuzzy: LabelMatch | None = None
        for k in range(1, min(6, len(words)) + 1):
            head = fold(" ".join(words[:k]))
            if not head:
                continue
            if head in exact:
                best_exact = LabelMatch(exact[head], k, 100)
                continue
            if any(ch.isdigit() for ch in words[k - 1]):
                break  # on a atteint la valeur : inutile d'aller plus loin
            for label, code in self.labels:
                if len(label) < 5 or abs(len(label) - len(head)) > 3:
                    continue  # pas d'approximation sur les sigles courts (GB, PNN...)
                score = fuzz.ratio(head, label)
                if score >= min_score and (best_fuzzy is None or score > best_fuzzy.score):
                    best_fuzzy = LabelMatch(code, k, score)
        return best_exact or best_fuzzy


# ---------------------------------------------------------------- unités
def unit_key(u: str) -> str:
    u = unicodedata.normalize("NFKC", u).replace("µ", "u").replace("μ", "u")
    u = u.replace("³", "3").replace("^", "").replace(" ", "").replace("−", "-")
    return u.lower()


def candidate_units(p: ParameterDef) -> dict[str, float]:
    """unité affichée -> facteur vers l'unité canonique (canonique incluse, facteur 1)."""
    return {p.unit: 1.0, **p.alt_units}


def resolve_unit(p: ParameterDef, raw: str | None) -> tuple[str | None, float | None, float]:
    """Rapproche l'unité lue d'une unité connue du paramètre. Renvoie (unité, facteur, score 0-100)."""
    if not raw:
        return None, None, 0.0
    key = unit_key(raw)
    units = candidate_units(p)
    for u, f in units.items():
        if unit_key(u) == key:
            return u, f, 100.0
    best = max(units.items(), key=lambda kv: fuzz.ratio(unit_key(kv[0]), key))
    score = fuzz.ratio(unit_key(best[0]), key)
    return (best[0], best[1], score) if score >= 60 else (None, None, score)


def infer_unit_by_magnitude(p: ParameterDef, value: float) -> tuple[str, float] | None:
    """Unité manquante ou illisible : on retient l'unique unité qui rend la valeur plausible."""
    lo, hi = p.plausible
    by_factor: dict[float, str] = {}
    for u, f in candidate_units(p).items():
        if lo <= value * f <= hi:
            by_factor.setdefault(f, u)  # unités équivalentes (même facteur) : une seule hypothèse
    if len(by_factor) != 1:
        return None
    f, u = next(iter(by_factor.items()))
    return u, f


def is_plausible(p: ParameterDef, canonical: float) -> bool:
    lo, hi = p.plausible
    return lo <= canonical <= hi


# ---------------------------------------------------------------- nombres
_OCR_DIGITS = str.maketrans({"O": "0", "o": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8"})
# Ponctuation tolérée autour d'un nombre (guillemets, parenthèses, points de conduite AVANT le nombre).
# Pas de point final : « 4... » est un reste de points de conduite, pas une valeur.
NUM_RE = re.compile(r"^[\"'«»(\[*.:~_-]*([<>]?)(\d+(?:[.,]\d+)?)[)\]»\"';*]*$")


def parse_number(token: str, allow_ocr_fix: bool = False) -> tuple[float, bool] | None:
    """Renvoie (valeur, corrigé_par_OCR). Accepte virgule ou point décimal."""
    t = re.sub(r"(?<=\d)[\u202f\u00a0 ](?=\d{3}\b)", "", token.strip())  # 12 400 -> 12400
    m = NUM_RE.match(t)
    fixed = False
    if not m and allow_ocr_fix:
        digits = sum(c.isdigit() for c in t)
        if digits >= 1 and digits >= len(t) - 2:
            m = NUM_RE.match(t.translate(_OCR_DIGITS))
            fixed = m is not None
    if not m or m.group(1):  # « < 5 » est une borne, pas un résultat
        return None
    return float(m.group(2).replace(",", ".")), fixed
