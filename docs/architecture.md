# Architecture

> Détail des choix : `docs/PLAN.md` §7 et `docs/DECISIONS.md`. Diagrammes UML : `docs/uml/` (PlantUML, rendu via l'extension VS Code PlantUML ou https://www.plantuml.com).

## 1. Composants

```mermaid
flowchart LR
  subgraph Client
    B[Navigateur<br/>React + TS]
  end
  subgraph Docker Compose
    P[Caddy<br/>TLS, proxy]
    FE[frontend<br/>Vite build statique]
    API[backend<br/>FastAPI]
    DB[(PostgreSQL 16)]
    FS[(volume storage<br/>fichiers, Grad-CAM, PDF)]
    VEC[(ChromaDB embarqué<br/>T3)]
  end
  subgraph Hôte Windows
    OL[Ollama<br/>llama3.2:3b]
  end
  B -- HTTPS --> P
  P --> FE
  P -- /api --> API
  API --> DB
  API --> FS
  API --> VEC
  API -- host.docker.internal:11434 --> OL
```

## 2. Découpage du backend

| Couche | Rôle |
|---|---|
| `api/` | Routes REST, contrôle d'accès (`current_user`, `require_role`, `get_patient_for_doctor`) |
| `schemas/` | Modèles Pydantic d'entrée/sortie |
| `services/ingestion` | Texte/OCR, classification, extraction, orchestration des jobs |
| `services/normalize` | Synonymes, unités, contexte, plausibilité, dédoublonnage |
| `services/trends`, `services/alerts` | Theil-Sen, qualification, moteur de règles YAML |
| `services/imaging` | Prétraitement, inférence TorchXRayVision, Grad-CAM, augmentation à l'inférence |
| `services/summary` | Faits, gabarit, LLM, vérificateur, PDF |
| `services/llm` | Client Ollama unique (timeouts, schéma JSON, journalisation) |
| `services/rag` | Index, recherche, réponse citée (T3) |
| `core/` | Configuration, sécurité (JWT, bcrypt), journalisation, audit |
| `db/` | Modèles SQLAlchemy, session, migrations Alembic |

## 3. Flux de données principal

```mermaid
flowchart TD
  U[Dépôt PDF / scan / radio] --> J[Job en file]
  J --> T{Type de fichier}
  T -- PDF natif --> X1[PyMuPDF : texte + boîtes]
  T -- scan --> X2[Prétraitement + Tesseract fra]
  T -- radio --> R1[Contrôles : adulte, vue frontale, qualité]
  X1 & X2 --> C[Classification règles → LLM en repli]
  C --> E[Extraction parseurs/regex → LLM en repli]
  E --> N[Normalisation]
  N --> V[Validation par le médecin]
  V --> M[(Mesures validées)]
  R1 --> R2[Scores + Grad-CAM + incertitude]
  R2 --> I[(Imagerie)]
  M --> TR[Tendances] --> AL[Alertes]
  M & I & AL --> D[Tableau de bord : courbes, frise, radios]
  M & I & AL --> F[Faits → gabarit → LLM optionnel → vérificateur → PDF]
```

## 4. Principes transverses

- **Isolation** : toute requête patient passe par `get_patient_for_doctor` ; l'admin n'a pas accès aux données patient.
- **Traçabilité** : chaque sortie IA stocke la version du modèle et du référentiel ; chaque action est journalisée.
- **Asynchrone simple** : BackgroundTasks FastAPI + table `jobs` ; pas de Celery ni de Redis.
- **LLM local** : un seul client `services/llm`, aucun autre chemin réseau sortant.
