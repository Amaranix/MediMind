"""Ablation de la fiche (étape 9.4) : d'où viennent les nombres que le LLM écrit ?

Trois conditions, pour chaque patient de démonstration chargé dans l'instance (A01, B01, C01) :
- `gabarit`          : fiche par gabarit (chiffres recopiés des faits par le code) ;
- `llm_brut`         : le LLM local résume le texte brut des derniers documents (aucun fait calculé) ;
- `llm_faits`        : le LLM résume les faits calculés par le code (mode rédaction assistée, 1 essai).
Chaque texte produit est passé au vérificateur (`assist.verify`) contre les faits du patient : part des nombres et
dates justifiés, et part des textes acceptés tels quels. Le vérificateur reste le même dans les trois cas.

Usage (instance lancée, Ollama sur l'hôte) : backend/.venv/Scripts/python evaluation/run_sheet_ablation.py [--runs 2]
Sortie : evaluation/results/sheet_ablation.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import warnings
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")

from app.services import assist, llm  # noqa: E402
from load_synthetic_patient import Client  # noqa: E402

PATIENTS = {"A01": ("Alaoui", "bpco"), "B01": ("Kettani", "pneumonie"), "C01": ("Alaoui", "fibrose")}
RAW_CHARS = 6000  # contexte du petit modèle : les derniers documents seulement


def raw_text(code: str) -> str:
    docs = sorted((ROOT / "synthetic" / "out" / code / "documents").glob("*.pdf"), reverse=True)
    parts, size = [], 0
    for p in docs:
        with pymupdf.open(p) as d:
            t = "\n".join(page.get_text() for page in d).strip()
        if size + len(t) > RAW_CHARS:
            break
        parts.append(f"--- {p.name}\n{t}")
        size += len(t)
    return "\n".join(parts)


def numbers_ratio(check: dict) -> float:
    bad = sum(1 for i in check["issues"] if i.startswith(("nombre", "date", "mois")))
    return 1 - bad / check["checked"] if check["checked"] else 1.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://localhost:8443")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--template-only", action="store_true", help="Recalculer la seule condition gabarit (sans LLM)")
    args = ap.parse_args()
    warnings.filterwarnings("ignore")
    api = Client(args.base, "berrada@medimind.local", "demo-pneumo-2026")
    patients = api.get("/patients")
    rows = []
    for code, (last, cond) in PATIENTS.items():
        pid = next(p["id"] for p in patients if p["last_name"] == last and cond in p["conditions"])
        facts = api.get(f"/patients/{pid}/facts?as_of=2026-11-05")
        source = assist.digest(facts)
        sheet = api.send("POST", f"/patients/{pid}/sheets?as_of=2026-11-05")["html"]
        # partie rédigée de la fiche (paragraphe « Motif et contexte ») : comparable aux synthèses du LLM
        para = re.search(r"<h2>Motif et contexte</h2>\s*<p>(.*?)</p>", sheet, flags=re.S).group(1)
        motif = re.sub(r"<sup>.*?</sup>|<[^>]+>", " ", para)
        rows.append({"patient": code, "condition": "gabarit", "run": 0, **assist.verify(motif, source), "seconds": 0.0})
        brut = raw_text(code)
        for run in range(0 if args.template_only else args.runs):
            for condition, prompt in (("llm_brut", f"Documents du dossier :\n{brut}"), ("llm_faits", f"Faits :\n{source}")):
                t0 = time.perf_counter()
                text = llm.generate_text(prompt, assist.SYSTEM) or ""
                check = assist.verify(text, source) if text else {"ok": False, "issues": ["vide"], "checked": 0}
                rows.append({"patient": code, "condition": condition, "run": run, **check, "text": text,
                             "seconds": round(time.perf_counter() - t0, 1)})
                print(f"{code} {condition:9s} run {run}: ok={check['ok']} nombres/dates justifiés "
                      f"{numbers_ratio(check):.0%} ({check['checked']}) {rows[-1]['seconds']} s", flush=True)

    out = ROOT / "evaluation" / "results" / "sheet_ablation.json"
    if args.template_only and out.exists():
        rows += [r for r in json.loads(out.read_text(encoding="utf-8"))["rows"] if r["condition"] != "gabarit"]
    summary = {}
    for condition in ("gabarit", "llm_brut", "llm_faits"):
        rs = [r for r in rows if r["condition"] == condition]
        checked = sum(r["checked"] for r in rs)
        bad = sum(sum(1 for i in r["issues"] if i.startswith(("nombre", "date", "mois"))) for r in rs)
        summary[condition] = {"textes": len(rs), "acceptés": sum(r["ok"] for r in rs),
                              "nombres_dates_vérifiés": checked, "non_justifiés": bad,
                              "part_justifiée": round(1 - bad / checked, 3) if checked else None,
                              "autres_erreurs": sum(sum(1 for i in r["issues"] if not i.startswith(("nombre", "date", "mois")))
                                                    for r in rs),
                              "secondes_moyennes": round(sum(r["seconds"] for r in rs) / len(rs), 1)}
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    for k, v in summary.items():
        print(k, v)


if __name__ == "__main__":
    main()
