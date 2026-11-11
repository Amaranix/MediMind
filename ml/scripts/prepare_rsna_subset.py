"""Prépare le sous-ensemble d'évaluation RSNA Pneumonia Detection Challenge (étape 1.2).

- Étiquette image : positive si « Lung Opacity » (opacité évocatrice de pneumonie, annotée par radiologues).
- Tirage stratifié reproductible, filtre adultes (âge DICOM >= 18), conversion DICOM -> PNG.
- Une image par patient (identifiant RSNA = une image).

Méthode : l'archive complète de la compétition (~3,9 Go) est téléchargée en une seule requête, puis seules
les images tirées sont lues dans le zip. Le téléchargement fichier par fichier déclenche la limitation de
débit de Kaggle (« rate limited ») au-delà de quelques centaines de requêtes.

Prérequis : règles de la compétition acceptées sur
https://www.kaggle.com/competitions/rsna-pneumonia-detection-challenge/rules

Usage : python ml/scripts/prepare_rsna_subset.py [--n-pos 500 --n-neg 1000] [--delete-zip]
Sorties : data/rsna_subset/images/*.png, data/rsna_subset/labels.csv
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import pydicom
from PIL import Image

COMP = "rsna-pneumonia-detection-challenge"
KAGGLE = str(Path(sys.executable).with_name("kaggle"))
ZIP_NAME = f"{COMP}.zip"


def download_archive(out: Path) -> Path:
    archive = out / ZIP_NAME
    if archive.exists() and zipfile.is_zipfile(archive):
        return archive
    for attempt in range(1, 7):
        print(f"Téléchargement de l'archive complète (tentative {attempt})...", flush=True)
        res = subprocess.run([KAGGLE, "competitions", "download", COMP, "-p", str(out)], text=True,
                             capture_output=True)
        if archive.exists() and zipfile.is_zipfile(archive):
            return archive
        msg = (res.stdout + res.stderr).strip().splitlines()[-1:] or [""]
        print(f"  échec : {msg[0]}", flush=True)
        if "rules" in msg[0].lower() or "access" in msg[0].lower():
            sys.exit("Acceptez les règles de la compétition sur Kaggle puis relancez.")
        time.sleep(120 * attempt)  # limitation de débit : attendre de plus en plus longtemps
    sys.exit("Archive RSNA introuvable après 6 tentatives.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/rsna_subset"))
    ap.add_argument("--n-pos", type=int, default=500)
    ap.add_argument("--n-neg", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--delete-zip", action="store_true", help="Supprimer l'archive après extraction")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    archive = download_archive(args.out)
    with zipfile.ZipFile(archive) as z:
        info = pd.read_csv(z.open("stage_2_detailed_class_info.csv")).drop_duplicates("patientId")
        info["label"] = (info["class"] == "Lung Opacity").astype(int)
        names = set(z.namelist())
        # Tirage reproductible dans tout le jeu, puis on lit les DICOM dans cet ordre jusqu'aux quotas adultes.
        order = info.sample(frac=1, random_state=args.seed)
        img_dir = args.out / "images"
        img_dir.mkdir(exist_ok=True)
        need = {1: args.n_pos, 0: args.n_neg}
        rows = []
        for _, r in order.iterrows():
            if need[r.label] == 0:
                continue
            member = f"stage_2_train_images/{r.patientId}.dcm"
            if member not in names:
                continue
            ds = pydicom.dcmread(io.BytesIO(z.read(member)))
            age = int(str(getattr(ds, "PatientAge", "0")).strip() or 0)
            if not 18 <= age <= 100:
                continue
            png = img_dir / f"{r.patientId}.png"
            if not png.exists():
                Image.fromarray(ds.pixel_array).convert("L").save(png)
            rows.append({"patient_id": r.patientId, "age": age, "sex": getattr(ds, "PatientSex", ""),
                         "view": getattr(ds, "ViewPosition", ""), "class": r["class"], "label": int(r.label)})
            need[r.label] -= 1
            if len(rows) % 250 == 0:
                print(f"{len(rows)} images retenues", flush=True)
            if not any(need.values()):
                break

    final = pd.DataFrame(rows)
    final.to_csv(args.out / "labels.csv", index=False)
    keep = set(final.patient_id)
    for f in img_dir.glob("*.png"):  # retire les images d'un ancien tirage
        if f.stem not in keep:
            f.unlink()
    for name in ("stage_2_train_labels.csv", "stage_2_detailed_class_info.csv"):
        with zipfile.ZipFile(archive) as z:
            (args.out / name).write_bytes(z.read(name))
    if args.delete_zip:
        archive.unlink()
    print(f"{len(final)} images adultes ({final.label.sum()} positives) -> {args.out / 'labels.csv'}")


if __name__ == "__main__":
    main()
