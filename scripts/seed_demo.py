"""Prépare l'instance de démonstration, uniquement par l'API (étape 8.3).

1. Crée le compte médecin de démonstration avec le compte administrateur du `.env` (s'il n'existe pas).
2. Charge B01 (pneumonie) et C01 (fibrose), entièrement validés.
3. Charge A01 (BPCO, patient de la démo) validé, SAUF :
   - le bilan scanné du 10/02/2026, laissé « à valider » (démonstration de l'OCR et de la conversion d'unité) ;
   - la visite du 05/11/2026 (EFR, bilan, compte rendu, radio R5), non déposée : elle se dépose en direct.
Relancer le script est sans risque : un document déjà présent est reconnu comme doublon.

Usage (pile lancée, depuis la racine) :
  backend/.venv/Scripts/python scripts/seed_demo.py            # Windows
  python scripts/seed_demo.py --base https://localhost:8443    # autre système (pip install httpx)
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_synthetic_patient import Client, load  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = {"name": "Dr Nadia Berrada", "email": "berrada@medimind.local", "password": "demo-pneumo-2026"}
LIVE_DAY = "2026-11-05"
KEEP_PENDING = frozenset({"2026-02-10_D002_bilan_bio.pdf"})


def env_file() -> dict[str, str]:
    path = ROOT / ".env"
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines()
    pairs = (line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))
    return {k.strip(): v.strip() for k, v in pairs}


def main() -> None:
    env = {**env_file(), **os.environ}
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=env.get("MEDIMIND_URL", "https://localhost:8443"))
    ap.add_argument("--admin-email", default=env.get("ADMIN_EMAIL"))
    ap.add_argument("--admin-password", default=env.get("ADMIN_PASSWORD"))
    args = ap.parse_args()
    if not (args.admin_email and args.admin_password):
        sys.exit("ADMIN_EMAIL et ADMIN_PASSWORD introuvables (fichier .env ou options).")
    warnings.filterwarnings("ignore")

    admin = Client(args.base, args.admin_email, args.admin_password)
    if not any(u["email"] == DOCTOR["email"] for u in admin.get("/users")):
        admin.send("POST", "/users", json={**DOCTOR, "role": "doctor"})
        print(f"Compte médecin créé : {DOCTOR['email']} / {DOCTOR['password']}")
    else:
        print(f"Compte médecin déjà présent : {DOCTOR['email']}")

    api = Client(args.base, DOCTOR["email"], DOCTOR["password"])
    for code in ("B01", "C01"):
        stats = load(api, code, validate=True)
        print(f"{code} chargé et validé ({sum(v for k, v in stats.items() if k.startswith('dépôt'))} fichiers).")
    live = frozenset(p.name for p in (ROOT / "synthetic" / "out" / "A01").rglob("*") if p.name.startswith(LIVE_DAY))
    stats = load(api, "A01", validate=True, skip=live, keep_pending=KEEP_PENDING)
    print(f"A01 chargé ({sum(v for k, v in stats.items() if k.startswith('dépôt'))} fichiers) ; bilan scanné du "
          "10/02/2026 laissé à valider.")
    print("\nÀ déposer en direct pendant la démonstration (patient Karim Alaoui) :")
    for p in sorted((ROOT / "synthetic" / "out" / "A01").rglob(f"{LIVE_DAY}*")):
        print(f"  {p.relative_to(ROOT)}")
    print(f"\nPrêt : {args.base} — {DOCTOR['email']} / {DOCTOR['password']}")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        sys.exit(f"Instance injoignable ou erreur de l'API : {exc}")
