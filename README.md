# MediMind

Application web d'**aide à la décision** pour pneumologues : suivi longitudinal de patients respiratoires adultes (biologie, EFR, traitements, radiographies thoraciques).

> **Démonstrateur de recherche (PFA 5IIR IA & Data, EMSI), non dispositif médical.** Données publiques ou synthétiques uniquement. Les résultats de l'IA ne constituent pas un diagnostic.

## Démarrage rapide

Prérequis : Docker Desktop, et [Ollama](https://ollama.com) sur la machine hôte avec le modèle `llama3.2:3b` (`ollama pull llama3.2:3b`).

```bash
cp .env.example .env        # puis remplacer chaque valeur « a-changer »
docker compose up -d --build --wait
```

Ouvrir **https://localhost:8443**. Le certificat est émis par l'autorité locale de Caddy : le navigateur demande de l'accepter une fois.

Le compte administrateur (`ADMIN_EMAIL` / `ADMIN_PASSWORD` du `.env`) est créé au premier démarrage. Il crée les comptes médecins depuis la page « Comptes » ; il n'a aucun accès aux dossiers des patients.

## Architecture

`proxy` (Caddy, HTTPS) → `frontend` (React) et `backend` (FastAPI, `/api`) → `db` (PostgreSQL 16) ; LLM local Ollama sur l'hôte. Détails : [`docs/architecture.md`](docs/architecture.md).

## Développement

```bash
# Backend
cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/ruff check . && .venv/Scripts/pytest
# Frontend (proxy /api vers http://localhost:8000)
cd frontend && npm ci && npm run dev
```

## Documentation

| Document | Contenu |
|---|---|
| [`docs/PLAN.md`](docs/PLAN.md) | Plan du projet : fonctionnalités, garde-fous, architecture, évaluation |
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | Étapes détaillées ; avancement dans [`docs/PROGRESS.md`](docs/PROGRESS.md) |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Décisions et écarts au cahier des charges |
| [`docs/data-sources.md`](docs/data-sources.md) | Jeux de données, licences, citations, régénération |
| [`docs/demo-scenario.md`](docs/demo-scenario.md) | Scénario de démonstration (patient A01) |

## Données et attributions

Radiographies : NIH ChestX-ray14 (Wang et al., CVPR 2017, NIH Clinical Center) et RSNA Pneumonia Detection Challenge (Shih et al., Radiol AI 2019). Dossiers cliniques : générateur synthétique du projet. Voir [`docs/data-sources.md`](docs/data-sources.md).
