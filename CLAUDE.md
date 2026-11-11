# MediMind AI

Application web d'aide à la décision pour pneumologues : suivi longitudinal de patients respiratoires **adultes** (biologie, EFR, traitements, radiographies). Démonstrateur de recherche PFA, **non dispositif médical**.

**Référence** : `docs/PLAN.md` (fonctionnalités, tranches T1/T2/T3, architecture, règles) et `docs/ROADMAP.md` (étapes détaillées, à suivre dans l'ordre). `MEDIMIND_AGENT_PLAN.md` est obsolète. Les écarts au cahier des charges sont dans `docs/PLAN.md` §13 ; toute nouvelle décision va dans `docs/DECISIONS.md`.

## Règles non négociables
- L'IA ne diagnostique jamais. Bandeau « aide à la décision » sur toute sortie IA.
- Courbes, alertes et fiches n'utilisent que des mesures validées par le médecin.
- Aucun nombre généré par un LLM : chiffres calculés par code, vérificateur obligatoire.
- LLM **local uniquement** (Ollama sur l'hôte, `host.docker.internal:11434`). Aucun appel externe avec des données patient.
- Règles et regex d'abord, LLM en repli.
- Données publiques ou synthétiques uniquement ; jamais de données réelles ni de secrets dans Git.
- Patients < 18 ans refusés.
- Chaque règle d'alerte cite sa source ; ne jamais modifier un seuil clinique sans le noter dans `DECISIONS.md`.
- Toute sortie IA stocke la version du modèle et la version du référentiel.

## Stack
Python 3.11, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2, PostgreSQL 16 · React + TS, Vite, Tailwind, Recharts · PyMuPDF, Tesseract `fra` · TorchXRayVision (CPU) · Docker Compose (db, backend, frontend, Caddy). Pas de Celery/Redis : BackgroundTasks + table `jobs`.

## Environnement
Windows 11, pas de GPU, 16 Go de RAM. Ollama : `llama3.2:3b` par défaut.

## Conventions
- Code, commits et identifiants en anglais ; interface et docs en français.
- Conventional Commits ; `main` toujours démontrable.
- Chaque fonctionnalité = code + test + doc courte ; mettre à jour `docs/PROGRESS.md`.

## Commandes
- Tout lancer : `docker compose up -d --build --wait` puis https://localhost:8443 (secrets dans `.env`, modèle `.env.example`)
- Backend : `cd backend && .venv/Scripts/ruff check . && .venv/Scripts/pytest`
- Migration : `cd backend && .venv/Scripts/alembic revision --autogenerate -m "..."` (contre un PostgreSQL), puis vérifier le fichier généré
- Frontend : `cd frontend && npm run lint && npm run build` ; dev : `npm run dev` (proxy /api -> :8000)
- Données : `.venv/Scripts/python -m synthetic.generator --seed 42` (voir `docs/data-sources.md`)
- Charger des patients de démo (pile lancée) : `backend/.venv/Scripts/python scripts/load_synthetic_patient.py A01 B01 C01 --validate`
- Évaluation extraction : `cd backend && TESSERACT_CMD="C:/Program Files/Tesseract-OCR/tesseract.exe" .venv/Scripts/python ../evaluation/run_extraction_eval.py --split dev` (ne jamais régler le pipeline sur `--split test`)

## Pièges connus
- Colonnes nommées `date` dans les modèles : annoter avec `dt.date` (import datetime as dt).
- Contexte de build du backend = racine du dépôt (inclut `referential/`) ; `.dockerignore` racine en liste blanche.
- Toutes les routes API sont sous `/api` ; toute route patient passe par `get_patient_for_doctor` (documents : `get_document_for_doctor`).
- Sessions SQLAlchemy sans autoflush : `db.flush()` avant de recompter des lignes modifiées dans la même requête.
- Remplacements de texte contenant des antislashs (regex, espaces insécables) : passer par un fichier de script ou l'outil Edit, jamais par un heredoc shell (apostrophes et échappements cassés).
