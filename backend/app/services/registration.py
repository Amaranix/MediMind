"""Recalage de deux radiographies et carte de différence (F-C8), avec scikit-image (déjà présent, T37).

1. Les deux clichés sont ramenés à 512 × 512, l'histogramme du récent est aligné sur celui de l'ancien (exposition).
2. Similitude (rotation, échelle, translation) : grille d'angles (−10° à +10°, pas de 1°) et d'échelles (0,90 à 1,10,
   pas de 0,02), affinée autour du meilleur couple (0,25° ; 0,01) ; pour chaque couple, translation par corrélation
   de phase. On garde la meilleure corrélation normalisée (calcul en 256 × 256, appliqué en 512). La corrélation de
   phase log-polaire a été écartée : le pic central du spectre la bloquait à 0°.
3. Carte : différence lissée (récent − ancien), rouge = plus dense sur le cliché récent, bleu = moins dense,
   transparente sous le seuil. La corrélation avant / après est renvoyée : sous 0,80, l'alignement est jugé
   insuffisant et l'interface le dit (la carte reflète alors surtout le positionnement).
Mesuré sur le patient A01 : corrélation 0,59 -> 0,89 (R1/R2), 0,61 -> 0,66 (R4/R5, inspiration différente).
Une différence peut venir du positionnement, de l'inspiration ou de l'exposition : ce n'est pas une lecture de lésion.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.exposure import match_histograms
from skimage.filters import gaussian
from skimage.registration import phase_cross_correlation
from skimage.transform import SimilarityTransform, resize, warp

from app.services.imaging import load_gray

SIZE = 512
WORK = 256
MAX_ANGLE = 10.0
SCALES = (0.90, 1.10)
SHOW_ABOVE = 0.10  # écart d'intensité (0..1) sous lequel la carte reste transparente
GOOD_ALIGNMENT = 0.80


@dataclass
class Registration:
    angle: float
    scale: float
    shift: tuple[float, float]
    ncc_before: float
    ncc_after: float
    png: bytes

    @property
    def reliable(self) -> bool:
        return self.ncc_after >= GOOD_ALIGNMENT


def _prep(path: Path) -> np.ndarray:
    gray, _ = load_gray(path)
    img = resize(gray, (SIZE, SIZE), anti_aliasing=True)
    lo, hi = np.percentile(img, (1, 99))
    return np.clip((img - lo) / max(hi - lo, 1e-6), 0, 1)


def _ncc(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-12))


def _transform(img: np.ndarray, angle: float, scale: float, shift: tuple[float, float]) -> np.ndarray:
    c = np.array(img.shape[::-1]) / 2
    to_center = SimilarityTransform(translation=-c)
    sim = SimilarityTransform(rotation=np.deg2rad(angle), scale=scale)
    back = SimilarityTransform(translation=c + np.array(shift[::-1]))
    return warp(img, (to_center + sim + back).inverse, mode="edge")


def _search(a: np.ndarray, b: np.ndarray, angles, scales) -> tuple[float, float, float, tuple[float, float]]:
    best = (-2.0, 0.0, 1.0, (0.0, 0.0))
    for sc in scales:
        for ang in angles:
            moved = _transform(b, float(ang), float(sc), (0.0, 0.0))
            shift, _, _ = phase_cross_correlation(a, moved, upsample_factor=10, normalization=None)
            shift = (float(shift[0]), float(shift[1]))
            score = _ncc(a, _transform(b, float(ang), float(sc), shift))
            if score > best[0]:
                best = (score, float(ang), float(sc), shift)
    return best


def _estimate(a: np.ndarray, b: np.ndarray) -> tuple[float, float, tuple[float, float]]:
    a2, b2 = resize(a, (WORK, WORK), anti_aliasing=True), resize(b, (WORK, WORK), anti_aliasing=True)
    _, ang, sc, _ = _search(a2, b2, np.arange(-MAX_ANGLE, MAX_ANGLE + 0.5, 1.0), np.arange(SCALES[0], SCALES[1] + 0.005, 0.02))
    _, ang, sc, shift = _search(a2, b2, np.arange(ang - 0.75, ang + 0.8, 0.25), np.arange(sc - 0.01, sc + 0.015, 0.01))
    k = SIZE / WORK
    return ang, sc, (shift[0] * k, shift[1] * k)


def register(path_old: Path, path_new: Path) -> Registration:
    a = _prep(path_old)
    b = match_histograms(_prep(path_new), a)
    angle, scale, shift = _estimate(a, b)
    b_al = _transform(b, angle, scale, shift)
    ncc_before, ncc_after = _ncc(a, b), _ncc(a, b_al)
    if ncc_after < ncc_before:  # recalage contre-productif : on garde l'image d'origine
        b_al, angle, scale, shift, ncc_after = b, 0.0, 1.0, (0.0, 0.0), ncc_before
    diff = gaussian(b_al - a, sigma=3)
    mag = np.clip((np.abs(diff) - SHOW_ABOVE) / 0.25, 0, 1)
    rgba = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
    rgba[..., 0] = np.where(diff > 0, 230, 40)
    rgba[..., 1] = np.where(diff > 0, 60, 120)
    rgba[..., 2] = np.where(diff > 0, 60, 235)
    rgba[..., 3] = (mag * 200).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    return Registration(round(angle, 2), round(scale, 3), (round(shift[0], 1), round(shift[1], 1)),
                        round(ncc_before, 3), round(ncc_after, 3), buf.getvalue())
