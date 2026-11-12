# Dossier de conception de MediMind (v1.0-rc)

> Démonstrateur de recherche, non dispositif médical. Ce dossier rassemble la conception livrée ; les détails vivent dans les documents cités.

## 1. Besoins

| Document | Contenu |
|---|---|
| `docs/CDC.pdf` | Cahier des charges initial |
| `docs/PLAN.md` | Plan validé : fonctionnalités F-A à F-E, garde-fous, architecture, évaluation, réglementation |
| `docs/user-stories.md` | 18 histoires d'utilisateur (médecin, administrateur) |
| `docs/DECISIONS.md` | Écarts au cahier des charges (D1 à D11) et décisions techniques (T1 à T40) |

**Acteurs** : le pneumologue (suit ses propres patients adultes) ; l'administrateur (gère les comptes, aucun accès aux dossiers).

**Exigences non négociables** : l'IA ne diagnostique jamais ; seules les données validées par le médecin sont utilisées ; aucun nombre généré par un LLM ; LLM local uniquement ; règles d'alerte sourcées ; versions des modèles et du référentiel stockées ; patients mineurs refusés.

## 2. Modèles UML

`docs/uml/` (PlantUML) : cas d'usage (`use-cases.puml`), séquence dépôt et validation (`sequence-upload-validation.puml`), séquence fiche pré-consultation (`sequence-consultation-sheet.puml`), diagramme de classes (`class-diagram.puml`). Rendu : extension PlantUML de VS Code ou https://www.plantuml.com. *Les deux séquences datent de la conception : la fiche n'utilise plus le LLM (T35).*

## 3. Architecture

Voir `docs/architecture.md` : 4 conteneurs Docker (proxy Caddy, frontend React, backend FastAPI, PostgreSQL) et Ollama sur l'hôte ; découpage du backend par service ; flux de données du dépôt à la fiche.

## 4. Modèle de données (PostgreSQL, migrations Alembic 0001 à 0006)

| Table | Rôle | Liens principaux |
|---|---|---|
| `users` | Comptes (médecin, administrateur), mot de passe bcrypt | |
| `patients` | Identité, antécédents, pathologies suivies (`conditions`) | médecin (`users`) |
| `documents` | Fichier déposé : type, date d'examen et leur origine, texte et boîtes OCR, statut, avertissements | patient |
| `parameters` | Copie du référentiel (synonymes, unités, plages, seuil significatif) | |
| `measurements` | Valeur extraite : paramètre, valeur canonique, contexte, confiance, boîte, statut de validation | patient, document |
| `treatments` | Ligne d'ordonnance : molécule, classe, posologie, durée, statut | patient, document |
| `clinical_events` | Exacerbation, hospitalisation, pneumonie, changement de traitement | patient, document (facultatif) |
| `imaging` | Scores, incertitude, contrôles de qualité, vue, modèle et version, lecture et annotations du médecin | document |
| `radiograph_comparisons` | Jugement d'évolution du médecin entre deux clichés | patient, deux documents |
| `alerts` | Alerte calculée : règle, date, valeurs, version du référentiel, acquittement | patient |
| `consultation_sheets` | Fiche : faits, HTML, mode, contrôle, chemin du PDF | patient |
| `document_chunks` | Passage d'un document validé et son plongement (assistant) | patient, document |
| `conversations` | Questions à l'assistant et réponses citées | médecin, patient |
| `audit_log` | Journal : qui, quoi, quel objet, quand | |
| `jobs` | Tâches de fond (lecture, analyse) : statut, essais, erreur | |

Toutes les tables d'un patient sont supprimées en cascade avec lui (vérifié par test).

## 5. Interface de programmation

Toutes les routes sont sous `/api` et documentées par FastAPI (`/api/docs`).

| Domaine | Routes principales |
|---|---|
| Authentification | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/me` |
| Comptes (administrateur) | `GET/POST /users`, `PATCH /users/{id}` |
| Patients | `GET/POST /patients`, `GET/PATCH/DELETE /patients/{id}` |
| Documents et validation | `POST/GET /patients/{id}/documents`, `GET/PATCH /documents/{id}`, `/documents/{id}/pages/{n}`, `/documents/{id}/measurements`, `PATCH /measurements/{id}`, `POST /documents/{id}/validate-confident`, `/documents/{id}/clinical`, `PATCH /treatments/{id}`, `PATCH/DELETE /events/{id}`, `POST /patients/{id}/events` |
| Évolution | `GET /patients/{id}/series`, `/trends`, `/timeline`, `/alerts`, `/periods`, `/facts`, `POST /alerts/{id}/acknowledge` |
| Imagerie | `GET /patients/{id}/imaging`, `POST/PATCH /documents/{id}/imaging`, `GET /documents/{id}/gradcam`, `/documents/{a}/difference/{b}` (+ `/image`), `GET /patients/{id}/radiograph-comparisons`, `PUT /radiograph-comparisons` |
| Fiche et assistant | `POST /patients/{id}/sheets`, `GET /sheets/{id}/pdf`, `GET/POST /patients/{id}/assistant` |
| Système | `GET /health`, `/referential`, `/jobs/{id}`, `POST /jobs/{id}/retry`, `GET /audit` |

## 6. Choix techniques

Résumé des décisions (détail et justification : `docs/DECISIONS.md`).

| Sujet | Choix | Décision |
|---|---|---|
| LLM | Local (Ollama, `llama3.2:3b`), repli seulement | D3, T2, T33 à T35 |
| Fiche | Gabarit déterministe, PDF par PyMuPDF | D4, T32, T35 |
| Extraction | Règles et gabarits d'abord ; OCR Tesseract avec prétraitement | T14 à T18 |
| Courbes | SVG maison sur un axe du temps partagé | T19 |
| Imagerie | TorchXRayVision CPU, incertitude, Grad-CAM, pas de verdict d'évolution | D5, D11, T25 à T30 |
| Assistant | Réponses lues en base, passages cités, sans génération ; sans ChromaDB | T36 |
| Recalage | scikit-image (similitude) au lieu d'OpenCV | T37 |
| Fiabilité | Pool de 40 connexions | T38 |
| Reproductibilité | Patients de démonstration versionnés, `seed_demo.py` | T39 |

## 7. Sécurité

Voir `docs/security-checklist.md` : HTTPS et en-têtes, CSP stricte (T40), sessions, limitation des connexions, isolation, fichiers, suppression en cascade, audit, secrets.

## 8. Qualité et évaluation

146 tests automatisés (couverture des services 91 %), test de bout en bout Playwright, intégration continue ; évaluation finale : `docs/evaluation-report.md` ; modèles : `docs/model-card.md`.
