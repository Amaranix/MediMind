"""Comparaison de deux périodes (F-B8), sur les seules mesures validées.

Par paramètre et par période : nombre de mesures, moyenne, minimum, maximum, dernière valeur, tendance (Theil-Sen,
qualification du référentiel si au moins `min_points` mesures). Écart des moyennes (B − A) qualifié comme une
tendance : sous le seuil cliniquement significatif (mcid) du référentiel => « stable », sinon amélioration ou
dégradation selon le sens d'amélioration du paramètre. Pour un paramètre « dans la zone » (better: range), on
compare la distance à la zone de référence.
"""
from __future__ import annotations

import datetime as dt
from statistics import mean

from app.services.referential import Referential
from app.services.trends import Point, _distance_to_range, qualify


def _stats(points: list[Point]) -> dict | None:
    if not points:
        return None
    values = [p.value for p in points]
    last = max(points, key=lambda p: p.date)
    return {"n": len(points), "mean": mean(values), "min": min(values), "max": max(values),
            "last": last.value, "last_date": last.date,
            "document_ids": sorted({p.document_id for p in points if p.document_id})}


def compare_periods(ref: Referential, series: dict[str, list[Point]], a: tuple[dt.date, dt.date],
                    b: tuple[dt.date, dt.date]) -> list[dict]:
    min_points = int(ref.trend_qualification.get("min_points", 3))
    order = {p.code: i for i, p in enumerate(ref.parameters)}
    out = []
    for code in sorted(series, key=order.__getitem__):
        p = ref.parameter(code)
        pa = [x for x in series[code] if a[0] <= x.date <= a[1]]
        pb = [x for x in series[code] if b[0] <= x.date <= b[1]]
        if not pa and not pb:
            continue
        sa, sb = _stats(pa), _stats(pb)
        row = {"param": code, "name": p.name, "unit": p.unit, "a": sa, "b": sb,
               "trend_a": qualify(p, pa, min_points)["qualification"] if pa else None,
               "trend_b": qualify(p, pb, min_points)["qualification"] if pb else None,
               "diff": None, "qualification": "insufficient"}
        if sa and sb:
            diff = sb["mean"] - sa["mean"]
            row["diff"] = diff
            if p.better == "range":
                da, db = _distance_to_range(p, sa["mean"]), _distance_to_range(p, sb["mean"])
                moved = abs(db - da) >= p.mcid.abs
                row["qualification"] = ("improving" if db < da else "worsening") if moved else "stable"
            elif abs(diff) < p.mcid.abs:
                row["qualification"] = "stable"
            else:
                row["qualification"] = "improving" if (diff > 0) == (p.better == "higher") else "worsening"
        out.append(row)
    return out
