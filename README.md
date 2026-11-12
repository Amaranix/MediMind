# MediMind

Application web d'**aide à la décision** pour pneumologues : suivi longitudinal de patients respiratoires adultes (biologie, EFR, traitements, radiographies thoraciques).

> **Démonstrateur de recherche (PFA 5IIR IA & Data, EMSI), non dispositif médical.** Données publiques ou synthétiques uniquement. Les résultats de l'IA ne constituent pas un diagnostic.

## Démarrage rapide

Prérequis : **Docker Desktop** (≈ 5 Go d'espace disque pour les images) et **Python 3.11** pour le script de démonstration. [Ollama](https://ollama.com) avec `llama3.2:3b` est facultatif : il ne sert qu'en repli quand les règles ne reconnaissent pas un document.

```bash
git clone https://github.com/Amaranix/MediMind.git && cd MediMind
cp .env.example .env              # puis remplacer chaque valeur « a-changer » (mots de passe, JWT_SECRET)
docker compose up -d --build --wait   # premier lancement : plusieurs minutes (PyTorch et modèles d'IA téléchargés)
pip install httpx                 # seule dépendance du script ci-dessous
python scripts/seed_demo.py       # compte médecin de démo + 3 patients fictifs (≈ 2 min 20)
```

Ouvrir **https://localhost:8443** et accepter une fois le certificat local (autorité interne de Caddy).

- **Médecin de démonstration** : `berrada@medimind.local` / `demo-pneumo-2026` (patients A01 BPCO, B01 pneumonie, C01 fibrose).
- **Administrateur** (`ADMIN_EMAIL` / `ADMIN_PASSWORD` du `.env`) : gestion des comptes, aucun accès aux dossiers.
- **Scénario de démonstration** : [`docs/demo-scenario.md`](docs/demo-scenario.md). Le script affiche les 4 documents du 05/11/2026 à déposer en direct sur le patient Karim Alaoui (A01) ; le bilan scanné du 10/02/2026 est laissé « à valider ».

Le port se change avec `HTTPS_PORT` et `SITE_ADDRESS` dans `.env` (même port dans les deux). Tout effacer : `docker compose down -v`.

## Architecture

`proxy` (Caddy, HTTPS) → `frontend` (React) et `backend` (FastAPI, `/api`) → `db` (PostgreSQL 16) ; LLM local Ollama sur l'hôte. Détails : [`docs/architecture.md`](docs/architecture.md).

## Développement et tests

```bash
# Backend : lint, tests, couverture des services (au moins 80 %)
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/ruff check . && .venv/Scripts/pytest --cov=app/services
# Frontend (proxy /api vers http://localhost:8000)
cd frontend && npm ci && npm run lint && npm run build && npm run dev
# De bout en bout (pile lancée + seed sur une instance neuve) et budgets de performance
pip install -r e2e/requirements.txt && python -m playwright install chromium
pytest e2e && python scripts/perf.py
```

La CI (GitHub Actions) enchaîne lint, tests et couverture, build du frontend, puis pile complète + seed + scénario Playwright.

## Documentation

| Document | Contenu |
|---|---|
| [`docs/PLAN.md`](docs/PLAN.md) | Plan du projet : fonctionnalités, garde-fous, architecture, évaluation |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Étapes détaillées ; avancement dans [`docs/PROGRESS.md`](docs/PROGRESS.md) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Décisions et écarts au cahier des charges |
| [`docs/data-sources.md`](docs/data-sources.md) | Jeux de données, licences, citations, régénération |
| [`docs/demo-scenario.md`](docs/demo-scenario.md) | Scénario de démonstration (patient A01) |
| [`docs/security-checklist.md`](docs/security-checklist.md) | Checklist sécurité et limites assumées |

## Données et attributions

Radiographies : NIH ChestX-ray14 (Wang et al., CVPR 2017, NIH Clinical Center) et RSNA Pneumonia Detection Challenge (Shih et al., Radiol AI 2019). Dossiers cliniques : générateur synthétique du projet. Voir [`docs/data-sources.md`](docs/data-sources.md).
