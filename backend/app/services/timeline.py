"""Frise des traitements et événements (F-D2, F-B3).

Barres de traitement :
- traitement court (durée connue) : du début à début + durée ;
- traitement au long cours : continue tant que les ordonnances de fond suivantes le renouvellent ; il
  s'arrête à la première ordonnance de fond qui ne le contient plus.
Changements de traitement : déduits en comparant deux ordonnances de fond successives (ajouts, arrêts).
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Rx:
    molecule: str
    drug_class: str | None
    dosage: str | None
    start: dt.date
    duration_days: int | None
    document_id: str | None


@dataclass
class Bar:
    molecule: str
    drug_class: str | None
    dosage: str | None
    start: dt.date
    end: dt.date | None  # None = en cours
    long_term: bool
    documents: list[str] = field(default_factory=list)


def build_bars(rxs: list[Rx]) -> tuple[list[Bar], list[dict]]:
    bars: list[Bar] = []
    for r in rxs:
        if r.duration_days:
            bars.append(Bar(r.molecule, r.drug_class, r.dosage, r.start,
                            r.start + dt.timedelta(days=r.duration_days), False, [r.document_id] if r.document_id else []))

    # Ordonnances de fond : regroupées par date
    fond: dict[dt.date, list[Rx]] = defaultdict(list)
    for r in rxs:
        if not r.duration_days:
            fond[r.start].append(r)
    dates = sorted(fond)
    open_bars: dict[str, Bar] = {}
    changes: list[dict] = []
    previous: set[str] | None = None
    for d in dates:
        current = {r.molecule for r in fond[d]}
        for mol, bar in list(open_bars.items()):
            if mol not in current:
                bar.end = d
                del open_bars[mol]
        for r in fond[d]:
            if r.molecule in open_bars:
                if r.document_id:
                    open_bars[r.molecule].documents.append(r.document_id)
                continue
            bar = Bar(r.molecule, r.drug_class, r.dosage, d, None, True, [r.document_id] if r.document_id else [])
            open_bars[r.molecule] = bar
            bars.append(bar)
        if previous is not None and current != previous:
            changes.append({"date": d, "added": sorted(current - previous), "stopped": sorted(previous - current)})
        previous = current
    bars.sort(key=lambda b: (not b.long_term, b.start, b.molecule))
    return bars, changes
