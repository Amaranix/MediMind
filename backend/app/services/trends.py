"""Séries temporelles et tendances (F-B4).

- Une série ne contient que des mesures validées ou corrigées par le médecin (garde-fou n° 1).
- Spirométrie : les mesures pré-bronchodilatateur sont exclues des courbes et des tendances (on suit le
  post-BD, ou la mesure sans test de réversibilité).
- Pente : estimateur de Theil-Sen (médiane des pentes deux à deux), robuste aux valeurs aberrantes.
- Qualification : variation ajustée sur la période comparée au seuil cliniquement significatif (mcid)
  du paramètre dans le référentiel, et au sens d'amélioration (`better`).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from statistics import median

from app.services.referential import ParameterDef, Referential


@dataclass(frozen=True)
class Point:
    date: dt.date
    value: float
    context: tuple[str, ...] = ()
    measurement_id: str | None = None
    document_id: str | None = None


def in_series(param: str, context: list[str] | tuple[str, ...]) -> bool:
    return "pre_bd" not in context


def theil_sen(points: list[Point]) -> float | None:
    """Pente annuelle (unité du paramètre par an)."""
    slopes = []
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            days = (points[j].date - points[i].date).days
            if days:
                slopes.append((points[j].value - points[i].value) / (days / 365.25))
    return median(slopes) if slopes else None


def _distance_to_range(p: ParameterDef, v: float) -> float:
    lo = p.reference.low if p.reference else None
    hi = p.reference.high if p.reference else None
    if lo is not None and v < lo:
        return lo - v
    if hi is not None and v > hi:
        return v - hi
    return 0.0


def qualify(p: ParameterDef, points: list[Point], min_points: int) -> dict:
    pts = sorted(points, key=lambda x: x.date)
    base = {"param": p.code, "n": len(pts), "unit": p.unit}
    if len(pts) < min_points:
        return {**base, "qualification": "insufficient"}
    first, last = pts[0], pts[-1]
    slope = theil_sen(pts)
    span_years = (last.date - first.date).days / 365.25
    change = (slope or 0.0) * span_years
    delta_abs = last.value - first.value
    out = {**base, "slope_per_year": slope, "change": change, "delta_abs": delta_abs,
           "delta_rel": delta_abs / first.value if first.value else None, "first": first.date, "last": last.date,
           "first_value": first.value, "last_value": last.value, "mcid": p.mcid.abs}
    if p.better == "range":
        d_first, d_last = _distance_to_range(p, first.value), _distance_to_range(p, last.value)
        moved = abs(d_last - d_first) >= p.mcid.abs
        q = ("improving" if d_last < d_first else "worsening") if moved else "stable"
    elif abs(change) < p.mcid.abs:
        q = "stable"
    else:
        q = "improving" if (change > 0) == (p.better == "higher") else "worsening"
    return {**out, "qualification": q}


def trends(ref: Referential, series: dict[str, list[Point]]) -> list[dict]:
    min_points = int(ref.trend_qualification.get("min_points", 3))
    return [qualify(ref.parameter(code), pts, min_points) for code, pts in series.items() if pts]
