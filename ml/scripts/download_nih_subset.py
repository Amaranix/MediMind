"""Télécharge uniquement les images NIH listées dans le manifest (Kaggle : nih-chest-xrays/data).

Les images sont réparties dans 12 dossiers `images_XXX/images/` par plages d'identifiants.
Le script devine le dossier par plage, essaie les dossiers voisins en cas d'échec, ignore
les fichiers déjà présents (relance possible) et écrit les images à plat dans data/nih_subset/images/.

Usage : python ml/scripts/download_nih_subset.py [--workers 4]
Prérequis : jeton Kaggle (~/.kaggle/access_token).
"""
from __future__ import annotations

import argparse
import bisect
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

DATASET = "nih-chest-xrays/data"
# Première image de chaque dossier images_001 ... images_012
FOLDER_STARTS = ["00000001_000", "00001336_000", "00003923_014", "00006585_007", "00009232_004", "00011558_008",
                 "00013774_026", "00016051_010", "00018387_035", "00020945_050", "00024717_001", "00028173_003"]
KAGGLE = str(Path(sys.executable).with_name("kaggle"))


def guess_folder(image: str) -> int:
    return bisect.bisect_right(FOLDER_STARTS, image.removesuffix(".png"))  # 1..12


def fetch(image: str, out_dir: Path) -> tuple[str, str]:
    target = out_dir / image
    if target.exists() and target.stat().st_size > 0:
        return image, "déjà présent"
    first = guess_folder(image)
    for folder in dict.fromkeys([first, first - 1, first + 1]):
        if not 1 <= folder <= 12:
            continue
        remote = f"images_{folder:03d}/images/{image}"
        for _attempt in range(3):  # Kaggle expire parfois : on réessaie
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    subprocess.run([KAGGLE, "datasets", "download", DATASET, "-f", remote, "-p", tmp, "--quiet"],
                                   capture_output=True, text=True, timeout=180)
                except subprocess.TimeoutExpired:
                    continue
                found = [p for p in Path(tmp).rglob(image)]
                if found:
                    shutil.move(str(found[0]), target)
                    return image, f"images_{folder:03d}"
                break  # pas dans ce dossier : essayer le voisin
    return image, "ÉCHEC"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=Path("data/nih_subset/manifest.csv"))
    ap.add_argument("--out", type=Path, default=Path("data/nih_subset/images"))
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    images = pd.read_csv(args.manifest)["image"].unique().tolist()
    args.out.mkdir(parents=True, exist_ok=True)
    failed = []
    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(fetch, im, args.out) for im in images]
        for i, fut in enumerate(as_completed(futures), 1):
            image, status = fut.result()
            if status == "ÉCHEC":
                failed.append(image)
            if i % 25 == 0 or status == "ÉCHEC":
                print(f"[{i}/{len(images)}] {image} : {status}", flush=True)
    print(f"Terminé : {len(images) - len(failed)}/{len(images)} images ; échecs : {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
