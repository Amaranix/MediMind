"""Sélectionne un sous-ensemble de patients NIH ChestX-ray14 pour les séries de démonstration.

Critères (docs/ROADMAP.md, étape 1.1) :
- adultes de 18 à 90 ans sur toutes les images retenues ;
- vues de face uniquement (PA ou AP) ;
- au moins 3 radiographies de face par patient ;
- 3 profils alignés sur les parcours cliniques :
    copd       : emphysème présent, pas de fibrose
    pneumonia  : pneumonie/consolidation présente puis au moins une image ultérieure sans,
                 pas d'emphysème ni de fibrose
    fibrosis   : fibrose présente, pas d'emphysème
- 20 patients par profil, équilibrés en sexe (10 F / 10 H), tirage reproductible.

Usage : python ml/scripts/select_nih_patients.py --csv data/nih_subset/Data_Entry_2017.csv
Sortie : data/nih_subset/manifest.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PROFILES = ("copd", "pneumonia", "fibrosis")
PNEUMONIA_LABELS = ("Pneumonia", "Consolidation")
MAX_IMAGES_PER_PATIENT = 6
PER_PROFILE = 20


def has(labels: pd.Series, *names: str) -> pd.Series:
    pattern = "|".join(names)
    return labels.str.contains(pattern, regex=True)


def profile_of(group: pd.DataFrame) -> str | None:
    labels = group["Finding Labels"]
    emph, fib = has(labels, "Emphysema").any(), has(labels, "Fibrosis").any()
    if emph and not fib:
        return "copd"
    if fib and not emph:
        return "fibrosis"
    if not emph and not fib:
        pos = has(labels, *PNEUMONIA_LABELS).to_numpy()
        if pos.any():
            first_pos = int(np.argmax(pos))
            if (~pos[first_pos + 1 :]).any():  # résolution observée après l'épisode
                return "pneumonia"
    return None


def pick_images(group: pd.DataFrame, profile: str) -> pd.DataFrame:
    """Garde au plus MAX_IMAGES_PER_PATIENT images : première, dernière et images clés, réparties dans le temps."""
    if len(group) <= MAX_IMAGES_PER_PATIENT:
        return group
    key_label = {"copd": ("Emphysema",), "fibrosis": ("Fibrosis",), "pneumonia": PNEUMONIA_LABELS}[profile]
    idx = list(range(len(group)))
    keep = {0, len(group) - 1}
    keep |= {i for i, pos in enumerate(has(group["Finding Labels"], *key_label)) if pos}
    if len(keep) > MAX_IMAGES_PER_PATIENT:
        ordered = sorted(keep)
        sel = np.linspace(0, len(ordered) - 1, MAX_IMAGES_PER_PATIENT).round().astype(int)
        keep = {ordered[i] for i in sel}
    rest = [i for i in idx if i not in keep]
    while len(keep) < MAX_IMAGES_PER_PATIENT and rest:
        sel = np.linspace(0, len(rest) - 1, MAX_IMAGES_PER_PATIENT - len(keep)).round().astype(int)
        keep |= {rest[i] for i in sel}
        rest = [i for i in idx if i not in keep]
    return group.iloc[sorted(keep)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=Path("data/nih_subset/Data_Entry_2017.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/nih_subset/manifest.csv"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    df = df.rename(columns={"Image Index": "image", "Patient ID": "patient_id", "Follow-up #": "follow_up",
                            "Patient Age": "age", "Patient Gender": "sex", "View Position": "view"})
    df = df[df["view"].isin(["PA", "AP"])]

    # Adultes uniquement, âges plausibles sur toutes les images du patient
    age_ok = df.groupby("patient_id")["age"].agg(lambda a: a.between(18, 90).all())
    df = df[df["patient_id"].isin(age_ok[age_ok].index)]
    counts = df.groupby("patient_id").size()
    df = df[df["patient_id"].isin(counts[counts >= 3].index)].sort_values(["patient_id", "follow_up"])

    rng = np.random.default_rng(args.seed)
    rows = []
    for profile in PROFILES:
        candidates = [pid for pid, g in df.groupby("patient_id") if profile_of(g) == profile]
        by_sex = {s: [p for p in candidates if df.loc[df.patient_id == p, "sex"].iloc[0] == s] for s in ("F", "M")}
        chosen = []
        for s, pool in by_sex.items():
            n = min(PER_PROFILE // 2, len(pool))
            chosen += list(rng.choice(pool, size=n, replace=False))
        print(f"{profile}: {len(candidates)} candidats, {len(chosen)} retenus")
        for pid in chosen:
            g = pick_images(df[df.patient_id == pid], profile)
            for rank, (_, r) in enumerate(g.iterrows()):
                rows.append({"profile": profile, "patient_id": int(pid), "rank": rank, "image": r["image"],
                             "follow_up": int(r["follow_up"]), "labels": r["Finding Labels"],
                             "age": int(r["age"]), "sex": r["sex"], "view": r["view"]})

    out = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f"{out.patient_id.nunique()} patients, {len(out)} images -> {args.out}")


if __name__ == "__main__":
    main()
