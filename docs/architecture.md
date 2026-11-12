# Architecture

> État livré (v1.0-rc). Détail des choix : `docs/PLAN.md` §7 et `docs/DECISIONS.md`. Diagrammes UML : `docs/uml/` (PlantUML). Dossier de conception complet : `docs/dossier-conception.md`.

## 1. Composants

```mermaid
flowchart LR
  subgraph Client
    B[Navigateur<br/>React + TypeScript]
  end
  subgraph Docker Compose
    P[proxy : Caddy<br/>HTTPS, en-têtes, CSP]
    FE[frontend<br/>build statique Vite]
    API[backend : FastAPI<br/>modèles d'imagerie et de recherche intégrés]
    DB[(db : PostgreSQL 16<br/>données, audit, passages indexés)]
    FS[(volume storage<br/>fichiers, cartes, PDF)]
  end
  subgraph Hôte
    OL[Ollama<br/>llama3.2:3b, repli de lecture]
  end
  B -- HTTPS :8443 --> P
  P --> FE
  P -- /api --> API
  API --> DB
  API --> FS
  API -- host.docker.internal:11434 --> OL
```

Seul le proxy publie un port. Les poids TorchXRayVision et le modèle `multilingual-e5-small` sont intégrés à l'image du backend (`HF_HUB_OFFLINE=1`) : aucune donnée ne sort de la machine.

## 2. Découpage du backend

| Couche | Rôle |
|---|---|
| `api/` | Routes REST sous `/api` : `auth`, `users`, `patients`, `documents`, `clinical` (séries, tendances, alertes, frise, faits, périodes), `imaging` (scores, Grad-CAM, annotations, jugement d'évolution, carte de différence), `sheets` (fiche), `assistant`, `system` ; contrôle d'accès par `current_user`, `require_role`, `get_patient_for_doctor` |
| `schemas/` | Modèles Pydantic d'entrée et de sortie |
| `services/ingestion/` | Texte et OCR (`text`), classification (`classify`), extraction (`extract`, `clinical`), normalisation (`normalize`), orchestration (`pipeline`, `job`) |
| `services/trends`, `alerts`, `periods`, `timeline` | Séries validées, Theil-Sen et qualification, moteur de règles du référentiel, comparaison de périodes, frise des traitements |
| `services/imaging`, `registration` | Inférence TorchXRayVision, incertitude, Grad-CAM, contrôles de qualité ; recalage et carte de différence |
| `services/facts`, `sheet`, `assist` | Dossier de faits, fiche par gabarit (Jinja2 → PDF PyMuPDF) ; rédaction assistée et vérificateur (évaluation seulement, T35) |
| `services/assistant`, `search` | Assistant du dossier : questions résolues en base, recherche sémantique de passages (e5) |
| `services/llm` | Client unique vers Ollama (délais, repli) |
| `core/` | Configuration, sécurité (JWT, bcrypt), limitation des connexions, journalisation |
| `db/` | Modèles SQLAlchemy, session (pool de 40 connexions, T38), migrations Alembic 0001 à 0006 |

## 3. Flux de données principal

```mermaid
flowchart TD
  U[Dépôt PDF / scan / photo / radiographie] --> J[Tâche de fond]
  J --> T{Type réel du fichier}
  T -- PDF natif --> X1[PyMuPDF : texte + boîtes]
  T -- scan ou photo --> X2[Redressement + médian + Otsu + Tesseract fra]
  T -- radiographie --> R1[Contrôles de qualité]
  X1 & X2 --> C[Classification : règles, LLM local en repli]
  C --> E[Extraction : gabarits et expressions, LLM en repli filtré]
  E --> N[Normalisation : synonymes, unités, contexte, plausibilité]
  N --> V[Validation par le médecin]
  V --> M[(Mesures, traitements, événements validés)]
  R1 --> R2[Scores ± incertitude, Grad-CAM]
  R2 --> I[(Imagerie)]
  M --> TR[Tendances] --> AL[Alertes sourcées]
  M & I & AL --> D[Tableau de bord : courbes, frise, tableau, périodes, radiographies]
  M & I & AL --> F[Faits → fiche par gabarit → PDF]
  M & I --> A[Assistant : requêtes en base + passages cités]
```

## 4. Principes transverses

- **Isolation** : toute route patient passe par `get_patient_for_doctor` (documents : `get_document_for_doctor`) ; l'administrateur n'a aucun accès aux dossiers.
- **Validation humaine** : courbes, alertes, faits, fiche et assistant ne lisent que les données validées ou corrigées.
- **Aucun chiffre généré par un LLM** : valeurs lues dans les documents, calculs par le code, sources citées.
- **Traçabilité** : version du modèle et du référentiel stockées avec chaque sortie d'IA ; journal d'audit de toutes les actions sensibles.
- **Asynchrone simple** : BackgroundTasks FastAPI + table `jobs` (relance, remise en échec au redémarrage) ; pas de Celery ni de Redis.
- **Local** : un seul chemin réseau sortant possible, vers Ollama sur l'hôte.
