"""Charge un ou plusieurs patients synthétiques dans une instance MediMind, uniquement par l'API.

1. crée le patient (identité de la vérité terrain) s'il n'existe pas ;
2. dépose tous ses documents et radiographies, attend la fin de la lecture ;
3. avec --validate, joue le rôle du médecin : chaque valeur, traitement ou événement extrait est comparé
   à la vérité terrain puis validé, corrigé ou rejeté (type et date du document corrigés si besoin).
   Les données « validées » sont donc celles qu'un médecin attentif aurait obtenues.

Le rapport affiché sert aussi de test de bout en bout de la chaîne d'ingestion.

Usage (depuis la racine, avec l'environnement du backend) :
  backend/.venv/Scripts/python scripts/load_synthetic_patient.py A01 --validate
  backend/.venv/Scripts/python scripts/load_synthetic_patient.py A01 B01 C01 --validate --base https://localhost:8443
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".png": "image/png"}


def close(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-3, 0.005 * abs(b))


class Client:
    def __init__(self, base: str, email: str, password: str):
        self.http = httpx.Client(base_url=base.rstrip("/") + "/api", verify=False, timeout=120)  # noqa: S501 - certificat local
        r = self.http.post("/auth/login", json={"email": email, "password": password})
        r.raise_for_status()
        self.http.headers["Authorization"] = f"Bearer {r.json()['access_token']}"

    def get(self, path: str):
        r = self.http.get(path)
        r.raise_for_status()
        return r.json()

    def send(self, method: str, path: str, **kw):
        r = self.http.request(method, path, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{method} {path} -> {r.status_code} {r.text[:200]}")
        return r.json() if r.content else None


def wait_idle(api: Client, pid: str, timeout: int = 600) -> list[dict]:
    t0 = time.time()
    while True:
        docs = api.get(f"/patients/{pid}/documents")
        if not any(d["status"] in ("uploaded", "processing") for d in docs):
            return docs
        if time.time() - t0 > timeout:
            raise TimeoutError("lecture des documents trop longue")
        time.sleep(1.5)


def load(api: Client, code: str, validate: bool) -> Counter:
    gt = json.loads((ROOT / "synthetic" / "ground_truth" / f"{code}.json").read_text(encoding="utf-8"))
    p = gt["patient"]
    stats: Counter = Counter()
    existing = [x for x in api.get("/patients") if x["last_name"] == p["last_name"] and x["first_name"] == p["first_name"]
                and x["birth_date"] == p["birth_date"]]
    conditions = [{"A": "bpco", "B": "pneumonie", "C": "fibrose"}[p["parcours"]]]
    if existing:
        pid = existing[0]["id"]
        if existing[0].get("conditions") != conditions:
            api.send("PATCH", f"/patients/{pid}", json={"conditions": conditions})
    else:
        pid = api.send("POST", "/patients", json={
            "first_name": p["first_name"], "last_name": p["last_name"], "birth_date": p["birth_date"], "sex": p["sex"],
            "height_cm": p["height_cm"], "pack_years": p["pack_years"], "conditions": conditions,
            "antecedents": {"A": "BPCO", "B": "Pneumonie communautaire", "C": "Pneumopathie interstitielle fibrosante"}[
                p["parcours"]]})["id"]
    by_name = {Path(d["file"]).name: d for d in gt["documents"]}
    files = sorted(by_name)
    for i in range(0, len(files), 8):
        batch = []
        for name in files[i:i + 8]:
            path = ROOT / "synthetic" / "out" / by_name[name]["file"]
            batch.append(("files", (name, path.read_bytes(), MIME[path.suffix])))
        for r in api.send("POST", f"/patients/{pid}/documents", files=batch):
            stats[f"dépôt_{r['status']}"] += 1
    docs = wait_idle(api, pid)
    if not validate:
        return stats

    # Type et date : corrigés comme le ferait le médecin
    for d in docs:
        g = by_name.get(d["original_name"])
        if not g:
            continue
        body = {}
        if d["type"] != g["type"]:
            body["type"] = g["type"]
            stats["type_corrigé"] += 1
        if d["exam_date"] != g["date"]:
            body["exam_date"] = g["date"]
            stats["date_corrigée"] += 1
        if body:
            api.send("PATCH", f"/documents/{d['id']}", json=body)
    docs = wait_idle(api, pid)

    for d in docs:
        g = by_name.get(d["original_name"])
        if not g:
            continue
        expected = list(g["printed"])
        for m in api.get(f"/documents/{d['id']}/measurements"):
            if m["validation_status"] not in ("pending", "suspect"):
                continue
            ctx = sorted(m["context"])
            same = [e for e in expected if e["param"] == m["parameter_code"] and sorted(e["context"]) == ctx]
            if same and close(m["value"], same[0]["canonical_value"]):
                api.send("PATCH", f"/measurements/{m['id']}", json={"action": "validate"})
                stats["valeur_validée"] += 1
                expected.remove(same[0])
            elif same:
                api.send("PATCH", f"/measurements/{m['id']}", json={"action": "correct",
                                                                     "value": same[0]["canonical_value"]})
                stats["valeur_corrigée"] += 1
                expected.remove(same[0])
            else:
                api.send("PATCH", f"/measurements/{m['id']}", json={"action": "reject"})
                stats["valeur_rejetée"] += 1
        stats["valeur_manquée"] += len(expected)

        clinical = api.get(f"/documents/{d['id']}/clinical")
        gt_trt = {t["molecule"]: t for t in g["treatments"]}
        for t in clinical["treatments"]:
            if t["validation_status"] != "pending":
                continue
            ref = gt_trt.get(t["molecule"])
            if ref is None:
                api.send("PATCH", f"/treatments/{t['id']}", json={"action": "reject"})
                stats["traitement_rejeté"] += 1
            elif ref["duration_days"] != t["duration_days"]:
                body = {"action": "correct", "long_term": ref["duration_days"] is None}
                if ref["duration_days"]:
                    body["duration_days"] = ref["duration_days"]
                api.send("PATCH", f"/treatments/{t['id']}", json=body)
                stats["traitement_corrigé"] += 1
            else:
                api.send("PATCH", f"/treatments/{t['id']}", json={"action": "validate"})
                stats["traitement_validé"] += 1
        gt_events = {(e["type"], e["date"]) for e in gt["events"]}
        for e in clinical["events"]:
            if e["validation_status"] != "pending":
                continue
            ok = (e["type"], e["date"]) in gt_events
            api.send("PATCH", f"/events/{e['id']}", json={"action": "validate" if ok else "reject"})
            stats["événement_validé" if ok else "événement_rejeté"] += 1
    # Événements absents des documents (ex. exacerbation non décrite) : saisis à la main par le médecin
    present = {(e["type"], e["date"]) for e in api.get(f"/patients/{pid}/timeline")["events"]}
    for e in gt["events"]:
        if e["type"] in ("exacerbation", "hospitalisation", "pneumonie") and (e["type"], e["date"]) not in present:
            api.send("POST", f"/patients/{pid}/events", json={"type": e["type"], "date": e["date"],
                                                              "end_date": e["end"], "note": e["note"]})
            stats["événement_saisi_à_la_main"] += 1
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("patients", nargs="+", help="Identifiants synthétiques (A01, B03...)")
    ap.add_argument("--base", default=os.environ.get("MEDIMIND_URL", "https://localhost:8443"))
    ap.add_argument("--email", default=os.environ.get("MEDIMIND_EMAIL", "berrada@medimind.local"))
    ap.add_argument("--password", default=os.environ.get("MEDIMIND_PASSWORD", "demo-pneumo-2026"))
    ap.add_argument("--validate", action="store_true", help="Simuler la validation par le médecin")
    args = ap.parse_args()
    import warnings
    warnings.filterwarnings("ignore")
    api = Client(args.base, args.email, args.password)
    total: Counter = Counter()
    for code in args.patients:
        t0 = time.time()
        s = load(api, code, args.validate)
        total += s
        print(f"{code} ({time.time() - t0:.0f} s) : " + ", ".join(f"{k} {v}" for k, v in sorted(s.items())), flush=True)
    if len(args.patients) > 1:
        print("TOTAL : " + ", ".join(f"{k} {v}" for k, v in sorted(total.items())))
    sys.exit(0)


if __name__ == "__main__":
    main()
