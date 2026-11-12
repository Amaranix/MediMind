"""Ablation de l'extraction (étape 9.5) : règles seules, LLM seul, hybride (règles puis LLM en repli).

Échantillon de documents de la partie test (bilans, EFR, comptes rendus ; PDF natifs, scans et photos), tiré au
hasard avec une graine fixe : le LLM local tourne sur CPU, 30 à 120 s par document en mode « LLM seul ».
- règles : `ingest_file(use_llm=False)` ;
- hybride : `ingest_file(use_llm=True)` (le LLM ne sert que si les règles ne reconnaissent rien) ;
- LLM seul : texte (PDF ou OCR identique) -> classification par le LLM -> extraction par le LLM, avec le même
  filtre que l'application (valeur présente mot pour mot dans le texte, paramètre connu, normalisation).
Mesures : précision, rappel, F1 des valeurs (même règle que run_extraction_eval) et durée par document.

Usage (depuis backend/, Ollama lancé) : .venv/Scripts/python ../evaluation/run_extraction_ablation.py [--n 15]
Sortie : evaluation/results/extraction_ablation.json.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")

from app.services import llm  # noqa: E402
from app.services.ingestion.pipeline import ingest_file, llm_fallback_values  # noqa: E402
from app.services.ingestion.text import extract  # noqa: E402
from app.services.referential import get_referential  # noqa: E402
from run_extraction_eval import MIME, prf, score  # noqa: E402


def llm_only(path: Path, mime: str, ref) -> tuple[str, list[dict]]:
    doc = extract(path, mime)
    guess = llm.classify_document(doc.text)
    values = llm_fallback_values(doc, ref)
    return (guess[0] if guess else "inconnu"), [{"param": v.param, "context": sorted(v.context), "value": v.value}
                                                for v in values]


def run(mode: str, d: dict, ref) -> dict:
    path = ROOT / "synthetic" / "out" / d["file"].replace("\\", "/")
    t0 = time.perf_counter()
    if mode == "llm_seul":
        doc_type, preds = llm_only(path, MIME[path.suffix], ref)
    else:
        res = ingest_file(path, MIME[path.suffix], ref, use_llm=(mode == "hybride"))
        doc_type = res.doc_type
        preds = [{"param": v.param, "context": sorted(v.context), "value": v.value} for v in res.values]
    tp, fp, fn = score(d["printed"], preds)
    return {"doc": d["doc_id"], "format": d["format"], "type_ok": doc_type == d["type"], "tp": len(tp), "fp": len(fp),
            "fn": len(fn), "seconds": round(time.perf_counter() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15)
    args = ap.parse_args()
    ref = get_referential()
    splits = json.loads((ROOT / "synthetic" / "splits.json").read_text(encoding="utf-8"))
    docs = []
    for pid in splits["test"]:
        g = json.loads((ROOT / "synthetic" / "ground_truth" / f"{pid}.json").read_text(encoding="utf-8"))
        docs += [d for d in g["documents"] if d["type"] in ("bilan_bio", "efr", "compte_rendu") and d["printed"]]
    sample = random.Random(42).sample(docs, min(args.n, len(docs)))  # noqa: S311 - tirage reproductible, pas de sécurité
    results = {}
    for mode in ("regles", "hybride", "llm_seul"):
        rows = []
        for d in sample:
            rows.append(run(mode, d, ref))
            print(f"{mode:8s} {d['doc_id']} {d['format']:9s} tp {rows[-1]['tp']} fp {rows[-1]['fp']} fn {rows[-1]['fn']} "
                  f"{rows[-1]['seconds']} s", flush=True)
        m = prf(sum(r["tp"] for r in rows), sum(r["fp"] for r in rows), sum(r["fn"] for r in rows))
        results[mode] = {**m, "classification": round(sum(r["type_ok"] for r in rows) / len(rows), 3),
                         "secondes_moyennes": round(sum(r["seconds"] for r in rows) / len(rows), 1), "rows": rows}
    out = ROOT / "evaluation" / "results" / "extraction_ablation.json"
    out.write_text(json.dumps({"documents": [d["doc_id"] for d in sample], **results}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    for mode, r in results.items():
        print(f"{mode:8s} P={r['precision']:.3f} R={r['recall']:.3f} F1={r['f1']:.3f} classification {r['classification']:.0%} "
              f"{r['secondes_moyennes']} s/doc")


if __name__ == "__main__":
    main()
