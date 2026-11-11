"""Génère evaluation/questions_60.jsonl : 60 questions cliniques (20 par parcours), réponses calculées
depuis la vérité terrain, avec les documents sources attendus.

Usage : python -m synthetic.generator.questions
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GT = ROOT / "synthetic" / "ground_truth"
OUT = ROOT / "evaluation" / "questions_60.jsonl"


def fr(x: float, dec: int) -> str:
    return f"{x:.{dec}f}".replace(".", ",")


def fd(s: str) -> str:
    return date.fromisoformat(s).strftime("%d/%m/%Y")


def series(g: dict, param: str, ctx: str | None = None) -> list[tuple[str, float, str]]:
    out = [(d["date"], v["canonical_value"], d["doc_id"]) for d in g["documents"] for v in d["printed"]
           if v["param"] == param and (ctx is None or ctx in v["context"])]
    return sorted(out)


def q_A(g: dict, k: int) -> dict:
    fev = series(g, "FEV1", "post_bd")
    exa = [e for e in g["events"] if e["type"] == "exacerbation"]
    kinds = [
        lambda: (f"Quel était le VEMS post-bronchodilatateur le {fd(fev[2][0])} ?", f"{fr(fev[2][1], 2)} L",
                 {"param": "FEV1", "value": fev[2][1], "unit": "L"}, [fev[2][2]], "valeur_a_date"),
        lambda: (f"De combien le VEMS post-bronchodilatateur a-t-il varié entre le {fd(fev[0][0])} et le {fd(fev[-1][0])} ?",
                 f"{round((fev[-1][1] - fev[0][1]) * 1000):+d} mL",
                 {"param": "FEV1", "delta": round(fev[-1][1] - fev[0][1], 3), "unit": "L"}, [fev[0][2], fev[-1][2]], "variation"),
        lambda: ("Combien d'exacerbations le patient a-t-il présentées sur la période suivie ?", str(len(exa)),
                 {"count": len(exa)}, [], "comptage_evenements"),
        lambda: ("À quelle date le traitement de fond a-t-il été renforcé par salmétérol/fluticasone ?",
                 fd(next(t["start"] for t in g["treatments"] if t["molecule"] == "salmétérol/fluticasone")),
                 {"date": next(t["start"] for t in g["treatments"] if t["molecule"] == "salmétérol/fluticasone")},
                 [next(t["source_doc"] for t in g["treatments"] if t["molecule"] == "salmétérol/fluticasone")], "traitement"),
        lambda: (f"Quelle était la CRP lors de l'exacerbation du {fd(exa[0]['date'])} ?",
                 f"{fr(next(v for d, v, _ in series(g, 'CRP') if d == exa[0]['date']), 1)} mg/L",
                 {"param": "CRP", "value": next(v for d, v, _ in series(g, "CRP") if d == exa[0]["date"]), "unit": "mg/L"},
                 [next(doc for d, _, doc in series(g, "CRP") if d == exa[0]["date"])], "valeur_a_date"),
    ]
    return kinds[k % len(kinds)]()


def q_B(g: dict, k: int) -> dict:
    crp = series(g, "CRP")
    abx = sorted((t for t in g["treatments"] if t["class"] == "antibiotic"), key=lambda t: t["start"])
    start = abx[0]["start"]
    norm = next(((d, v, doc) for d, v, doc in crp if d > start and v < 5), None)
    switch = len(abx) > 1
    kinds = [
        lambda: ("Quelle était la CRP au diagnostic de la pneumonie ?", f"{fr(crp[0][1], 1)} mg/L",
                 {"param": "CRP", "value": crp[0][1], "unit": "mg/L"}, [crp[0][2]], "valeur_a_date"),
        lambda: (f"La CRP s'est-elle normalisée (< 5 mg/L) après l'antibiotique débuté le {fd(start)} ? Si oui, à quelle date ?",
                 f"Oui, le {fd(norm[0])} ({fr(norm[1], 1)} mg/L)" if norm else "Non",
                 {"normalized": bool(norm), "date": norm[0] if norm else None}, [norm[2]] if norm else [], "normalisation"),
        lambda: ("Un relais antibiotique a-t-il été nécessaire ? Si oui, par quelle molécule ?",
                 f"Oui, {abx[1]['molecule']} le {fd(abx[1]['start'])}" if switch else "Non",
                 {"switch": switch, "molecule": abx[1]["molecule"] if switch else None},
                 [abx[1]["source_doc"]] if switch else [], "traitement"),
        lambda: ("Quelle antibiothérapie a été prescrite au diagnostic, et pour combien de jours ?",
                 f"{abx[0]['molecule']}, {abx[0]['duration_days']} jours",
                 {"molecule": abx[0]["molecule"], "duration_days": abx[0]["duration_days"]}, [abx[0]["source_doc"]], "traitement"),
    ]
    return kinds[k % len(kinds)]()


def q_C(g: dict, k: int) -> dict:
    fvc, dlco, spo2 = series(g, "FVC_PRED"), series(g, "DLCO_PRED"), series(g, "SPO2")
    anti = next(t for t in g["treatments"] if t["class"] == "antifibrotic")
    kinds = [
        lambda: (f"Quelle était la CVF en pourcentage de la valeur prédite le {fd(fvc[1][0])} ?", f"{fvc[1][1]:.0f} %",
                 {"param": "FVC_PRED", "value": fvc[1][1], "unit": "%"}, [fvc[1][2]], "valeur_a_date"),
        lambda: (f"Quelle est la variation absolue de la CVF (% prédit) entre le {fd(fvc[0][0])} et le {fd(fvc[-1][0])} ?",
                 f"{fvc[-1][1] - fvc[0][1]:+.0f} points", {"param": "FVC_PRED", "delta": fvc[-1][1] - fvc[0][1]},
                 [fvc[0][2], fvc[-1][2]], "variation"),
        lambda: (f"Quelle est la variation absolue de la DLCO (% prédit) entre le {fd(dlco[0][0])} et le {fd(dlco[-1][0])} ?",
                 f"{dlco[-1][1] - dlco[0][1]:+.0f} points", {"param": "DLCO_PRED", "delta": dlco[-1][1] - dlco[0][1]},
                 [dlco[0][2], dlco[-1][2]], "variation"),
        lambda: ("Quel traitement antifibrosant a été introduit, et à quelle date ?", f"{anti['molecule']}, le {fd(anti['start'])}",
                 {"molecule": anti["molecule"], "date": anti["start"]}, [anti["source_doc"]], "traitement"),
        lambda: ("Quelle est la dernière SpO2 au repos en air ambiant ?", f"{spo2[-1][1]:.0f} % le {fd(spo2[-1][0])}",
                 {"param": "SPO2", "value": spo2[-1][1], "date": spo2[-1][0]}, [spo2[-1][2]], "valeur_a_date"),
    ]
    return kinds[k % len(kinds)]()


def main() -> None:
    gens = {"A": q_A, "B": q_B, "C": q_C}
    rows = []
    for parcours in "ABC":
        files = sorted(GT.glob(f"{parcours}*.json"))
        for k in range(20):
            g = json.loads(files[k % len(files)].read_text(encoding="utf-8"))
            question, answer, value, sources, qtype = gens[parcours](g, k)
            rows.append({"id": f"Q{len(rows) + 1:02d}", "patient_id": g["patient"]["id"], "split": g["split"],
                         "parcours": parcours, "type": qtype, "question": question, "answer": answer,
                         "answer_value": value, "source_doc_ids": sources})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    print(f"{len(rows)} questions -> {OUT}")


if __name__ == "__main__":
    main()
