"""Prépare le sous-ensemble d'évaluation RSNA Pneumonia Detection Challenge (étape 1.2).

- Étiquette image : positive si « Lung Opacity » (opacité évocatrice de pneumonie, annotée par radiologues).
- Tirage stratifié reproductible (1/3 positives), téléchargement fichier par fichier,
  filtre adultes (âge DICOM >= 18) et vue de face, conversion DICOM -> PNG.
- Une image par patient (identifiant RSNA = une image).

Prérequis : règles de la compétition acceptées sur
https://www.kaggle.com/competitions/rsna-pneumonia-detection-challenge/rules

Usage : python ml/scripts/prepare_rsna_subset.py [--n-pos 500 --n-neg 1000 --workers 6]
Sorties : data/rsna_subset/images/*.png, data/rsna_subset/labels.csv
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom
from PIL import Image

COMP = "rsna-pneumonia-detection-challenge"
KAGGLE = str(Path(sys.executable).with_name("kaggle"))
OVERSAMPLE = 1.25  # marge pour compenser les mineurs exclus


def kaggle_file(remote: str, dest: Path) -> Path | None:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run([KAGGLE, "competitions", "download", COMP, "-f", remote, "-p", tmp, "--quiet"],
                       capture_output=True, text=True, timeout=300)
        files = list(Path(tmp).rglob("*"))
        for f in files:
            if f.suffix == ".zip":
                with zipfile.ZipFile(f) as z:
                    z.extractall(tmp)
        name = Path(remote).name
        hits = [f for f in Path(tmp).rglob(name) if f.is_file()]
        if not hits:
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        hits[0].replace(dest)
        return dest


def fetch_and_convert(pid: str, out_dir: Path) -> dict | None:
    png = out_dir / f"{pid}.png"
    with tempfile.TemporaryDirectory() as tmp:
        dcm_path = kaggle_file(f"stage_2_train_images/{pid}.dcm", Path(tmp) / f"{pid}.dcm")
        if dcm_path is None:
            return None
        ds = pydicom.dcmread(dcm_path)
        age = int(str(getattr(ds, "PatientAge", "0")).strip() or 0)
        meta = {"patient_id": pid, "age": age, "sex": getattr(ds, "PatientSex", ""),
                "view": getattr(ds, "ViewPosition", "")}
        if age >= 18 and not png.exists():
            Image.fromarray(ds.pixel_array).convert("L").save(png)
        return meta


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/rsna_subset"))
    ap.add_argument("--n-pos", type=int, default=500)
    ap.add_argument("--n-neg", type=int, default=1000)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    for name in ("stage_2_train_labels.csv", "stage_2_detailed_class_info.csv"):
        if not (args.out / name).exists() and kaggle_file(name, args.out / name) is None:
            sys.exit(f"Téléchargement impossible de {name} : acceptez les règles de la compétition sur Kaggle.")

    info = pd.read_csv(args.out / "stage_2_detailed_class_info.csv").drop_duplicates("patientId")
    info["label"] = (info["class"] == "Lung Opacity").astype(int)
    rng = np.random.default_rng(args.seed)
    pos = info[info.label == 1].sample(int(args.n_pos * OVERSAMPLE), random_state=args.seed)
    neg = info[info.label == 0].sample(int(args.n_neg * OVERSAMPLE), random_state=args.seed)
    cand = pd.concat([pos, neg]).sample(frac=1, random_state=int(rng.integers(1 << 31)))

    img_dir = args.out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    metas = []
    with ThreadPoolExecutor(args.workers) as pool:
        futs = {pool.submit(fetch_and_convert, pid, img_dir): pid for pid in cand.patientId}
        for i, fut in enumerate(as_completed(futs), 1):
            m = fut.result()
            if m:
                metas.append(m)
            if i % 50 == 0:
                print(f"[{i}/{len(futs)}]", flush=True)

    meta = pd.DataFrame(metas).merge(info[["patientId", "class", "label"]], left_on="patient_id", right_on="patientId")
    adults = meta[meta.age >= 18]
    final = pd.concat([adults[adults.label == 1].head(args.n_pos), adults[adults.label == 0].head(args.n_neg)])
    final = final.drop(columns="patientId")
    final.to_csv(args.out / "labels.csv", index=False)
    keep = set(final.patient_id)
    for f in img_dir.glob("*.png"):  # retire les images non retenues
        if f.stem not in keep:
            f.unlink()
    print(f"{len(final)} images adultes ({final.label.sum()} positives) -> {args.out / 'labels.csv'}")


if __name__ == "__main__":
    main()
