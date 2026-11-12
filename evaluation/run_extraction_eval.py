"""Évaluation de l'ingestion (étapes 3.8 et 9.1) contre la vérité terrain du générateur synthétique.

Mesures : classification du document, date d'examen, puis précision / rappel / F1 des valeurs par paramètre,
par gabarit et par format (PDF natif, scan PDF, photo). Une valeur est correcte si paramètre, contexte
(pré/post-BD, repos, air ambiant...) et valeur canonique concordent (tolérance 0,5 % ou 0,001).

Usage (depuis backend/) :
  .venv/Scripts/python ../evaluation/run_extraction_eval.py --split dev [--workers 4] [--limit N] [--llm]
Sortie : evaluation/results/extraction_<split>.json et résumé à l'écran.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.ingestion.pipeline import ingest_file  # noqa: E402
from app.services.referential import get_referential  # noqa: E402

MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".png": "image/png"}


def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-3, 0.005 * abs(b))


def run_one(args: tuple[dict, bool]) -> dict:
    d, use_llm = args
    path = ROOT / "synthetic" / "out" / d["file"].replace("\\", "/")
    res = ingest_file(path, MIME[path.suffix], get_referential(), use_llm=use_llm)
    preds = [{"param": v.param, "context": sorted(v.context), "value": v.value, "conf": v.confidence,
              "flags": v.flags} for v in res.values]
    return {"doc_id": d["doc_id"], "pred_type": res.doc_type, "pred_date": str(res.exam_date) if res.exam_date else None,
            "preds": preds, "seconds": res.seconds}


def score(gt_vals: list[dict], preds: list[dict]) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """Renvoie (vrais positifs par paramètre, faux positifs, faux négatifs)."""
    used = set()
    tp, fn = [], []
    for g in gt_vals:
        ctx = sorted(g["context"])
        hit = next((i for i, p in enumerate(preds) if i not in used and p["param"] == g["param"]
                    and p["context"] == ctx and close(p["value"], g["canonical_value"])), None)
        if hit is None:
            fn.append(g["param"])
        else:
            used.add(hit)
            tp.append((g["param"], g["param"]))
    fp = [p["param"] for i, p in enumerate(preds) if i not in used]
    return tp, fp, fn


def prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--llm", action="store_true", help="Autoriser le repli LLM (plus lent)")
    args = ap.parse_args()

    splits = json.loads((ROOT / "synthetic" / "splits.json").read_text(encoding="utf-8"))
    docs = []
    for pid in splits[args.split]:
        g = json.loads((ROOT / "synthetic" / "ground_truth" / f"{pid}.json").read_text(encoding="utf-8"))
        docs += [{**d, "patient": pid} for d in g["documents"]]
    if args.limit:
        docs = docs[: args.limit]
    by_id = {d["doc_id"]: d for d in docs}

    with ProcessPoolExecutor(args.workers) as pool:
        results = list(pool.map(run_one, [(d, args.llm) for d in docs], chunksize=4))

    agg = defaultdict(lambda: [0, 0, 0])
    type_ok = date_ok = n_dated = 0
    errors = []
    for r in results:
        d = by_id[r["doc_id"]]
        type_ok += r["pred_type"] == d["type"]
        if d["type"] != "radiographie":
            n_dated += 1
            date_ok += r["pred_date"] == d["date"]
        tp, fp, fn = score(d["printed"], r["preds"])
        fmt = {"pdf": "pdf_natif", "scan_pdf": "scan_pdf", "photo_jpg": "photo", "png": "image"}[d["format"]]
        for p, _ in tp:
            for k in ("ALL", f"param:{p}", f"template:{d['template']}", f"format:{fmt}", f"type:{d['type']}"):
                agg[k][0] += 1
        for p in fp:
            for k in ("ALL", f"param:{p}", f"template:{d['template']}", f"format:{fmt}", f"type:{d['type']}"):
                agg[k][1] += 1
        for p in fn:
            for k in ("ALL", f"param:{p}", f"template:{d['template']}", f"format:{fmt}", f"type:{d['type']}"):
                agg[k][2] += 1
        if fp or fn or r["pred_type"] != d["type"]:
            errors.append({"doc": d["doc_id"], "file": d["file"], "template": d["template"], "format": fmt,
                           "type": [d["type"], r["pred_type"]], "fn": fn, "fp": fp})
    summary = {
        "split": args.split, "documents": len(results),
        "classification_accuracy": round(type_ok / len(results), 3),
        "date_accuracy": round(date_ok / n_dated, 3) if n_dated else None,
        "mean_seconds": round(sum(r["seconds"] for r in results) / len(results), 2),
        "max_seconds": max(r["seconds"] for r in results),
        "metrics": {k: prf(*v) for k, v in sorted(agg.items())},
    }
    out = ROOT / "evaluation" / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"extraction_{args.split}.json").write_text(
        json.dumps({**summary, "errors": errors}, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"{summary['documents']} documents | classification {summary['classification_accuracy']:.1%} | "
          f"date {summary['date_accuracy']:.1%} | {summary['mean_seconds']} s/doc (max {summary['max_seconds']} s)")
    for k, m in summary["metrics"].items():
        if k == "ALL" or k.split(":")[0] in ("format", "template", "type"):
            print(f"  {k:24s} P={m['precision']:.3f} R={m['recall']:.3f} F1={m['f1']:.3f}  "
                  f"(tp {m['tp']}, fp {m['fp']}, fn {m['fn']})")
    weak = [(k, m) for k, m in summary["metrics"].items() if k.startswith("param:") and m["f1"] < 0.95]
    for k, m in weak:
        print(f"  ! {k:22s} F1={m['f1']:.3f}  (tp {m['tp']}, fp {m['fp']}, fn {m['fn']})")
    print(f"{len(errors)} documents avec au moins une erreur -> {out / f'extraction_{args.split}.json'}")


if __name__ == "__main__":
    main()
