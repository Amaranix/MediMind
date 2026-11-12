"""Mesure des budgets de performance du PLAN §8 sur une instance lancée (étape 8.2), par l'API.

Budgets : courbes 1 an < 2 s ; PDF natif < 30 s ; scan < 60 s ; radiographie < 5 s ; fiche par gabarit < 5 s.
Un patient temporaire est créé, reçoit un PDF natif, un PDF scanné et une radiographie (patient de démo C01), puis
est supprimé. Les courbes et la fiche sont mesurées sur le patient le plus fourni du médecin de démo.
Code de sortie 1 si un budget est dépassé.

Usage (pile lancée, seed fait) : backend/.venv/Scripts/python scripts/perf.py [--base https://localhost:8443]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_synthetic_patient import MIME, Client, wait_idle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
BUDGETS = {"courbes_1_an": 2.0, "pdf_natif": 30.0, "scan": 60.0, "radiographie": 5.0, "fiche_gabarit": 5.0}


def timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://localhost:8443")
    ap.add_argument("--email", default="berrada@medimind.local")
    ap.add_argument("--password", default="demo-pneumo-2026")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    api = Client(args.base, args.email, args.password)
    results: dict[str, float] = {}

    gt = json.loads((ROOT / "synthetic" / "ground_truth" / "C01.json").read_text(encoding="utf-8"))
    pick = {fmt: next(d["file"].replace("\\", "/") for d in gt["documents"] if d["format"] == fmt)
            for fmt in ("pdf", "scan_pdf", "png")}
    pid = api.send("POST", "/patients", json={"first_name": "Perf", "last_name": "Mesure", "birth_date": "1970-01-01",
                                               "sex": "F"})["id"]
    try:
        for key, fmt in (("pdf_natif", "pdf"), ("scan", "scan_pdf"), ("radiographie", "png")):
            path = ROOT / "synthetic" / "out" / pick[fmt]
            t0 = time.perf_counter()
            api.send("POST", f"/patients/{pid}/documents", files=[("files", (path.name, path.read_bytes(), MIME[path.suffix]))])
            wait_idle(api, pid)
            results[key] = time.perf_counter() - t0  # dépôt + lecture complète, vu du médecin
    finally:
        api.send("DELETE", f"/patients/{pid}")

    patients = api.get("/patients")
    busiest = max(patients, key=lambda p: len(api.get(f"/patients/{p['id']}/documents")))
    since = (dt.date.today() - dt.timedelta(days=365)).isoformat()
    _, results["courbes_1_an"] = timed(lambda: (api.get(f"/patients/{busiest['id']}/series?from={since}"),
                                                api.get(f"/patients/{busiest['id']}/trends?from={since}"),
                                                api.get(f"/patients/{busiest['id']}/timeline")))
    _, results["fiche_gabarit"] = timed(lambda: api.send("POST", f"/patients/{busiest['id']}/sheets"))

    failed = False
    print(f"{'Mesure':16s} {'Durée':>8s} {'Budget':>8s}")
    for key, budget in BUDGETS.items():
        ok = results[key] <= budget
        failed |= not ok
        print(f"{key:16s} {results[key]:7.2f}s {budget:7.0f}s  {'OK' if ok else 'DÉPASSÉ'}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
