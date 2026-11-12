"""Évaluation de l'assistant du dossier (F-E4) sur `questions_60.jsonl`.

Les données de chaque patient sont construites depuis la vérité terrain du générateur (comme si le médecin avait
tout validé), puis passées au même cœur que l'application (`assistant.answer`). Mesures :
- exactitude : la valeur, l'écart, le compte, la date ou la molécule attendus sont dans la réponse (tolérances
  d'arrondi : 0,5 % ou 0,01 pour une valeur, 5 mL ou 0,5 point pour un écart) ;
- citations : les documents sources attendus sont tous cités.

Usage (depuis backend/) : .venv/Scripts/python ../evaluation/run_assistant_eval.py --split dev
Sortie : evaluation/results/assistant_<split>.json. Ne jamais régler l'assistant sur --split test.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.assistant import PatientData, Rx, answer  # noqa: E402
from app.services.referential import get_referential  # noqa: E402
from app.services.trends import Point, in_series  # noqa: E402


def patient_data(pid: str) -> PatientData:
    g = json.loads((ROOT / "synthetic" / "ground_truth" / f"{pid}.json").read_text(encoding="utf-8"))
    d = dt.date.fromisoformat
    series: dict[str, list[Point]] = {}
    docs = {}
    for doc in g["documents"]:
        docs[doc["doc_id"]] = {"type": doc["type"], "date": d(doc["date"]), "name": doc["file"]}
        for v in doc["printed"]:
            if in_series(v["param"], v["context"]):
                series.setdefault(v["param"], []).append(
                    Point(d(doc["date"]), v["canonical_value"], tuple(v["context"]), None, doc["doc_id"]))
    reports = {(x["date"]): x["doc_id"] for x in g["documents"] if x["type"] == "compte_rendu"}
    events = [{"type": e["type"], "date": d(e["date"]), "end_date": d(e["end"]) if e.get("end") else None,
               "document_id": reports.get(e["date"])} for e in g["events"]]
    rx = [Rx(t["molecule"], t["class"], t.get("dosage"), d(t["start"]), t.get("duration_days"), t.get("source_doc"))
          for t in g["treatments"]]
    return PatientData({k: sorted(v, key=lambda p: p.date) for k, v in series.items()}, events, rx, docs)


def close(a, b, tol) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def correct(expected: dict, got: dict) -> bool:
    for key, want in expected.items():
        if key in ("param", "unit"):
            continue
        have = got.get("relay" if key == "switch" else key)
        if key == "value":
            ok = close(have, want, max(0.01, 0.005 * abs(want)))
        elif key == "delta":
            ok = close(have, want, 0.005 if expected.get("unit") == "L" else 0.5)
        elif key == "date":
            ok = str(have) == want
        elif key == "molecule" and want is None:
            ok = True
        else:
            ok = have == want
        if not ok:
            return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], default="dev")
    args = ap.parse_args()
    ref = get_referential()
    lines = (ROOT / "evaluation" / "questions_60.jsonl").read_text(encoding="utf-8").splitlines()
    questions = [json.loads(line) for line in lines if line.strip()]
    questions = [q for q in questions if q["split"] == args.split]
    cache: dict[str, PatientData] = {}
    rows, by_type = [], Counter()
    for q in questions:
        data = cache.setdefault(q["patient_id"], patient_data(q["patient_id"]))
        a = answer(ref, data, q["question"])
        ok = correct(q["answer_value"], a.data)
        cited = set(q["source_doc_ids"]) <= set(a.citations)
        by_type[(q["type"], ok)] += 1
        rows.append({"id": q["id"], "type": q["type"], "question": q["question"], "expected": q["answer"],
                     "answer": a.text, "kind": a.kind, "correct": ok, "citations_ok": cited,
                     "citations": a.citations, "expected_sources": q["source_doc_ids"]})
    n = len(rows)
    summary = {"split": args.split, "questions": n, "accuracy": round(sum(r["correct"] for r in rows) / n, 3),
               "citations": round(sum(r["citations_ok"] for r in rows) / n, 3),
               "by_type": {t: f"{by_type[(t, True)]}/{by_type[(t, True)] + by_type[(t, False)]}"
                           for t in sorted({r["type"] for r in rows})}}
    out = ROOT / "evaluation" / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"assistant_{args.split}.json").write_text(json.dumps({**summary, "rows": rows}, indent=1, ensure_ascii=False,
                                                                 default=str), encoding="utf-8")
    print(f"{n} questions | réponses justes {summary['accuracy']:.0%} | citations complètes {summary['citations']:.0%}")
    for t, v in summary["by_type"].items():
        print(f"  {t:22s} {v}")
    for r in rows:
        if not (r["correct"] and r["citations_ok"]):
            print(f"  ! {r['id']} {r['question']}\n      attendu : {r['expected']} {r['expected_sources']}\n"
                  f"      obtenu  : {r['answer']} {r['citations']}")


if __name__ == "__main__":
    main()
