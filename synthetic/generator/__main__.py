"""Génère les 36 dossiers synthétiques (12 par parcours), la vérité terrain et les splits.

Usage : python -m synthetic.generator --seed 42 [--only A01] [--no-render]

Sorties :
  synthetic/out/{id}/documents/*.pdf|*.jpg  documents (PDF natifs, scans, photos)
  synthetic/out/{id}/radiographies/*.png    radiographies NIH datées
  synthetic/ground_truth/{id}.json           vérité terrain (valeurs imprimées et canoniques, événements, traitements)
  synthetic/splits.json                      30 développement / 6 test (figé)
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pymupdf

from . import templates as T
from .clinical import PatientSim
from .render import PdfRenderer, degrade

ROOT = Path(__file__).resolve().parents[2]
SYN = ROOT / "synthetic"
NIH = ROOT / "data" / "nih_subset"
PER_PARCOURS = 12
SCAN_RATE = 0.30
DEMO_ID = "A01"


def pick_nih(manifest: pd.DataFrame, rng: np.random.Generator) -> dict[str, list[dict]]:
    """12 patients NIH par profil (6 F / 6 H). Le patient de démo A01 = homme BPCO 58-70 ans avec >= 4 radios."""
    chosen: dict[str, list[dict]] = {}
    for parcours, profile in (("A", "copd"), ("B", "pneumonia"), ("C", "fibrosis")):
        m = manifest[manifest.profile == profile]
        pats = []
        for sex in ("M", "F"):
            ids = sorted(m[m.sex == sex].patient_id.unique())
            pats += list(rng.choice(ids, size=PER_PARCOURS // 2, replace=False))
        if parcours == "A":
            g = m.groupby("patient_id").agg(n=("image", "size"), age=("age", "first"), sex=("sex", "first"))
            demo = g[(g.sex == "M") & g.age.between(58, 70) & (g.n >= 4)].index
            demo_id = int(demo[0])
            if demo_id in pats:
                pats.remove(demo_id)
            else:
                pats.remove(next(p for p in pats if g.loc[p, "sex"] == "M"))
            pats = [demo_id] + pats
        chosen[parcours] = []
        for pid in pats:
            rows = m[m.patient_id == pid].sort_values("rank")
            chosen[parcours].append({"patient_id": int(pid), "sex": rows.sex.iloc[0], "age": int(rows.age.iloc[0]),
                                     "images": rows[["image", "labels"]].to_dict("records")})
    return chosen


def make_splits(rng: np.random.Generator) -> dict:
    test = []
    for p in "ABC":
        pool = [f"{p}{i:02d}" for i in range(1, PER_PARCOURS + 1) if f"{p}{i:02d}" != DEMO_ID]
        test += sorted(rng.choice(pool, size=2, replace=False).tolist())
    dev = [f"{p}{i:02d}" for p in "ABC" for i in range(1, PER_PARCOURS + 1) if f"{p}{i:02d}" not in test]
    return {"seed_note": "Figé : ne pas régénérer avec une autre graine sans le noter dans docs/DECISIONS.md",
            "dev": dev, "test": test, "heldout_template": "T4",
            "demo_patient": DEMO_ID}


def build_documents(rec: dict, split: str, rng: np.random.Generator, out_dir: Path, renderer: PdfRenderer | None) -> None:
    p = rec["patient"]
    docs_dir, rx_dir = out_dir / "documents", out_dir / "radiographies"
    docs_dir.mkdir(parents=True, exist_ok=True)
    rx_dir.mkdir(parents=True, exist_ok=True)
    fav = str(rng.choice(["T1", "T2", "T3"]))
    prev_by_tpl: dict[str, dict[str, float]] = {}
    is_demo = p["id"] == DEMO_ID
    for d in rec["documents"]:
        stem = f"{d['date']}_{d['doc_id'].split('-')[-1]}_{d['type']}"
        if d["type"] == "radiographie":
            dest = rx_dir / f"{d['date']}_{d['doc_id'].split('-')[-1]}.png"
            shutil.copyfile(NIH / "images" / d["nih_image"], dest)
            d.update(template=None, format="png", file=str(dest.relative_to(SYN / "out")), printed=[])
            continue
        if d["type"] == "bilan_bio":
            if split == "test":
                tpl = "T4" if rng.random() < 0.5 else str(rng.choice(["T1", "T2", "T3"]))
            else:
                tpl = fav if rng.random() < 0.7 else str(rng.choice(["T1", "T2", "T3"]))
            html, printed = T.lab_report(tpl, p, d, prev_by_tpl.get(tpl, {}))
            prev_by_tpl[tpl] = {v["param"]: v["value"] for v in d["values"]}
        elif d["type"] == "efr":
            tpl, (html, printed) = "EFR", T.efr_report(p, d)
        elif d["type"] == "compte_rendu":
            tpl, (html, printed) = "CR", T.visit_report(p, d, rec["events"])
        else:
            tpl, (html, printed) = "ORD", T.prescription(p, d)
        fmt = "pdf"
        target = docs_dir / f"{stem}.pdf"
        if renderer:
            renderer.render(html, target)
            # Démo : le premier bilan d'exacerbation est un scan, pour montrer l'OCR en direct.
            scan = rng.random() < SCAN_RATE if not is_demo else (d["type"] == "bilan_bio" and d["date"] == "2026-02-10")
            if scan:
                as_photo = d["type"] == "ordonnance" or rng.random() < 0.3
                target = degrade(target, rng, as_photo)
                fmt = "photo_jpg" if as_photo else "scan_pdf"
        d.update(template=tpl, format=fmt, file=str(target.relative_to(SYN / "out")), printed=printed)


def check_native_text(rec: dict) -> list[str]:
    """Vérifie que chaque valeur imprimée figure dans le texte des PDF natifs."""
    errors = []
    for d in rec["documents"]:
        if d.get("format") != "pdf":
            continue
        text = pymupdf.open(SYN / "out" / d["file"])[0].get_text().replace(" ", " ")
        for pv in d["printed"]:
            if pv["printed"].replace(" ", " ") not in text:
                errors.append(f"{d['doc_id']} {pv['param']} '{pv['printed']}' absent")
    return errors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--only", help="Générer un seul patient (ex. A01)")
    ap.add_argument("--no-render", action="store_true", help="Simulation seule, sans PDF")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    manifest = pd.read_csv(NIH / "manifest.csv")
    nih = pick_nih(manifest, rng)
    splits = make_splits(rng)
    (SYN / "splits.json").write_text(json.dumps(splits, indent=2, ensure_ascii=False), encoding="utf-8")
    (SYN / "ground_truth").mkdir(parents=True, exist_ok=True)

    renderer = None if args.no_render else PdfRenderer().__enter__()
    all_errors: list[str] = []
    try:
        for parcours in "ABC":
            for i, nih_p in enumerate(nih[parcours], 1):
                pid = f"{parcours}{i:02d}"
                prng = np.random.default_rng([args.seed, ord(parcours), i])  # graine stable par patient
                if args.only and pid != args.only:
                    continue
                demo = pid == DEMO_ID
                start = date(2025, 11, 20) if demo else start_date(parcours, nih_p, prng)
                sim = PatientSim(pid, parcours, nih_p, prng, start)
                if demo:
                    sim.first, sim.last, sim.age, sim.height, sim.pack_years = "Karim", "Alaoui", 64, 172, 40
                    sim.birth = date(1962, 3, 14)
                if parcours == "A":
                    sim.simulate_A(demo=demo)
                elif parcours == "B":
                    sim.simulate_B()
                else:
                    sim.simulate_C(progressive=i <= 8)
                rec = sim.record()
                split = "test" if pid in splits["test"] else "dev"
                rec["split"] = split
                out_dir = SYN / "out" / pid
                if out_dir.exists():
                    shutil.rmtree(out_dir)
                if renderer:
                    build_documents(rec, split, prng, out_dir, renderer)
                    errs = check_native_text(rec)
                    all_errors += errs
                (SYN / "ground_truth" / f"{pid}.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False),
                                                                  encoding="utf-8")
                n_docs = len(rec["documents"])
                n_vals = sum(len(d["values"]) for d in rec["documents"])
                print(f"{pid} ({split}) {p_name(rec)} : {n_docs} documents, {n_vals} valeurs", flush=True)
    finally:
        if renderer:
            renderer.__exit__(None, None, None)
    if all_errors:
        print(f"{len(all_errors)} incohérences texte/vérité terrain :", *all_errors[:20], sep="\n  ")
        raise SystemExit(1)
    print("Vérité terrain cohérente avec le texte de tous les PDF natifs.")


LAST_DAY = date(2026, 11, 5)  # aucun document après cette date (dossiers dans le passé au moment de la démo)


def start_date(parcours: str, nih_p: dict, rng: np.random.Generator) -> date:
    """Date de début telle que le dernier document du parcours tombe avant LAST_DAY."""
    if parcours == "A":
        span = 365
    elif parcours == "C":
        span = 420
    else:  # B : radios antérieures espacées de 60 j, puis suivi jusqu'à J300
        labels = [im["labels"] for im in nih_p["images"]]
        first_pos = next(i for i, lab in enumerate(labels) if "Pneumonia" in lab or "Consolidation" in lab)
        span = 60 * first_pos + 300
    return LAST_DAY - timedelta(days=span + int(rng.integers(0, 90)))


def p_name(rec: dict) -> str:
    p = rec["patient"]
    return f"{p['first_name']} {p['last_name'][0]}."


if __name__ == "__main__":
    main()
