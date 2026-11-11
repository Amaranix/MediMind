"""Évaluation du modèle d'imagerie (étapes 5.5 et 9.3).

Deux mesures, pour rendre visible la fuite de données connue (docs/PLAN.md §6.1) :
- INTERNE (optimiste) : poids `densenet121-res224-all`, utilisés dans l'application. Ils ont été entraînés
  notamment sur NIH et RSNA : leur AUC sur ces jeux est surestimée.
- EXTERNE : poids `densenet121-res224-chex` (entraînés sur CheXpert seulement), évalués sur RSNA, jeu jamais vu.

Jeux :
- rsna : 1 image par patient, étiquette « Lung Opacity » (radiologues) ; scores Pneumonia, Lung Opacity,
  Consolidation comparés à cette étiquette.
- nih  : sous-ensemble de démonstration (étiquettes extraites automatiquement des comptes rendus).

Sorties : AUC avec intervalle de confiance à 95 % (bootstrap), sensibilité/spécificité au seuil 0,5,
analyse par sexe et tranche d'âge. Fichier evaluation/results/imaging_<jeu>.json.

Usage (depuis backend/) :
  .venv/Scripts/python ../evaluation/run_imaging_eval.py --dataset rsna
  .venv/Scripts/python ../evaluation/run_imaging_eval.py --dataset nih --limit 20     # vérification rapide
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

WEIGHTS = {"interne_all": "densenet121-res224-all", "externe_chex": "densenet121-res224-chex"}
RSNA_TARGETS = ["Lung Opacity", "Pneumonia", "Consolidation"]
NIH_TARGETS = ["Consolidation", "Effusion", "Atelectasis", "Emphysema", "Fibrosis", "Cardiomegaly", "Pneumonia",
               "Infiltration"]


def auc(y: np.ndarray, s: np.ndarray) -> float | None:
    """AUC = probabilité qu'un cas positif ait un score plus élevé qu'un négatif (Mann-Whitney)."""
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def auc_ci(y: np.ndarray, s: np.ndarray, n_boot: int = 1000, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    point = auc(y, s)
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        a = auc(y[idx], s[idx])
        if a is not None:
            boots.append(a)
    lo, hi = (np.percentile(boots, [2.5, 97.5]) if boots else (None, None))
    tp = int(((s >= 0.5) & (y == 1)).sum())
    tn = int(((s < 0.5) & (y == 0)).sum())
    return {"auc": round(point, 3) if point is not None else None,
            "ci95": [round(float(lo), 3), round(float(hi), 3)] if boots else None,
            "n": int(len(y)), "positives": int(y.sum()),
            "sensibilite_0_5": round(tp / max(1, int(y.sum())), 3),
            "specificite_0_5": round(tn / max(1, int((y == 0).sum())), 3)}


def load_model(weights: str):
    import torchxrayvision as xrv

    from app.services.imaging import XrayModel
    m = XrayModel.__new__(XrayModel)  # même prétraitement que l'application, autres poids
    import threading

    import torch
    m.torch, m.xrv = torch, xrv
    m.model = xrv.models.DenseNet(weights=weights)
    m.model.eval()
    m.pathologies = list(m.model.pathologies)
    m.version = f"torchxrayvision {xrv.__version__}"
    m.run_lock = threading.Lock()
    return m


def score_images(m, paths: list[Path]) -> pd.DataFrame:
    from app.services.imaging import load_gray
    rows = []
    for i, p in enumerate(paths, 1):
        gray, _ = load_gray(p)
        out = m.scores(m.to_tensor(m.preprocess(gray)))
        rows.append({name: float(v) for name, v in zip(m.pathologies, out, strict=True) if name})
        if i % 100 == 0:
            print(f"  {i}/{len(paths)}", flush=True)
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["rsna", "nih"], default="rsna")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--models", default="interne_all,externe_chex")
    args = ap.parse_args()

    if args.dataset == "rsna":
        meta = pd.read_csv(ROOT / "data" / "rsna_subset" / "labels.csv")
        meta["path"] = [ROOT / "data" / "rsna_subset" / "images" / f"{p}.png" for p in meta.patient_id]
        labels = {t: meta["label"].to_numpy() for t in RSNA_TARGETS}
    else:
        meta = pd.read_csv(ROOT / "data" / "nih_subset" / "manifest.csv")
        meta["path"] = [ROOT / "data" / "nih_subset" / "images" / i for i in meta.image]
        labels = {t: meta["labels"].str.contains(t).astype(int).to_numpy() for t in NIH_TARGETS}
    if args.limit:
        meta = meta.head(args.limit)
        labels = {k: v[: args.limit] for k, v in labels.items()}
    meta["age_group"] = pd.cut(meta["age"], [17, 40, 60, 120], labels=["18-40", "41-60", "> 60"])

    report = {"dataset": args.dataset, "n_images": len(meta), "models": {}}
    for key in args.models.split(","):
        weights = WEIGHTS[key]
        print(f"{key} ({weights}) sur {len(meta)} images…", flush=True)
        t0 = time.time()
        m = load_model(weights)
        scores = score_images(m, list(meta.path))
        res = {"weights": weights, "seconds_per_image": round((time.time() - t0) / len(meta), 3), "targets": {}}
        for target, y in labels.items():
            if target not in scores:
                continue
            s = scores[target].to_numpy()
            entry = {"global": auc_ci(y, s)}
            for col in ("sex", "age_group"):
                for g, idx in meta.groupby(col, observed=True).groups.items():
                    pos = meta.index.get_indexer(idx)
                    entry[f"{col}={g}"] = auc_ci(y[pos], s[pos], n_boot=300)
            res["targets"][target] = entry
        report["models"][key] = res
        for target, e in res["targets"].items():
            g = e["global"]
            print(f"  {target:14s} AUC {g['auc']} IC95 {g['ci95']} (n={g['n']}, positifs {g['positives']})")
    out = ROOT / "evaluation" / "results" / f"imaging_{args.dataset}{'_sample' if args.limit else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
