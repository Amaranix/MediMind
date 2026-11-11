# MediMind AI : Plan d'exécution complet pour agent (de A à Z)

> **Rôle de ce fichier** : brief unique à donner à un agent de développement (Claude Code ou équivalent). Il contient le contexte, les règles, l'architecture, les skills à utiliser, toutes les phases (S1 à S8) avec tâches, livrables et critères d'acceptation.
> **Projet** : PFA 5IIR IA & Data, EMSI Casablanca, Groupe 3, 2026/2027. Étudiants : LAMZOURI Ishak, AMRANI Ismail. Encadrant : Pr Adil CHERGUI.
> **Durée** : 8 semaines, MVP à la fin de S5. **Version du cahier des charges** : 1.0 (novembre 2026).

---

## 0. Règles d'or pour l'agent (à lire en premier)

1. **Un seul utilisateur cible** : le pneumologue. **Un seul fil conducteur** : le suivi longitudinal du patient respiratoire. Toute fonctionnalité qui n'y contribue pas est hors périmètre.
2. **MediMind AI est une aide à la décision**, jamais un diagnostic. Avertissement visible sur chaque résultat IA. Toute valeur extraite est validable/corrigeable par le médecin.
3. **Données publiques ou synthétiques uniquement.** Aucune donnée réelle de patient. Anonymiser (nom, identifiant, téléphone) avant tout appel à un LLM externe.
4. **Aucun chiffre inventé par le LLM.** Tous les nombres d'une fiche sont calculés par code ; le LLM rédige seulement ; un vérificateur contrôle que chaque nombre/date du texte existe dans les faits.
5. **Priorités** : P1 = indispensable (MVP), P2 = important, P3 = bonus. **Règle de coupe** en cas de retard après S5 : abandonner P3, puis les P2 du module E, puis les autres P2. **Les P1 ne sont jamais coupées.**
6. **Simplicité d'infrastructure** : pas de Celery/Redis. Tâches asynchrones = `BackgroundTasks` FastAPI + table `jobs`. Stockage fichiers = volume Docker.
7. **Chaque tâche livrée = code + test + doc courte**. Commits atomiques (Conventional Commits). Branche `main` toujours démontrable.
8. **Langue** : interface et documents patients en français ; code, commits et noms de variables en anglais ; docs de projet en français.
9. En cas d'ambiguïté non bloquante : choisir l'option la plus simple, l'écrire dans `docs/DECISIONS.md`, continuer.
10. Ne jamais désactiver les vérifications de sécurité ni committer de secrets (`.env` ignoré, `.env.example` fourni).

---

## 1. Skills à utiliser

### 1.1 Skills Claude (à charger avec l'outil Skill avant de produire le type de fichier concerné)

| Skill | Quand l'utiliser dans ce projet |
|---|---|
| `frontend-design` | Conception du tableau de bord React (écran unique de suivi, visionneuse comparative, fiche). Éviter l'esthétique générique. |
| `dataviz` | Courbes d'évolution (VEMS, CRP, scores IA), choix des couleurs, zones de référence, annotations d'événements, accessibilité clair/sombre. |
| `pdf` | Génération/lecture de PDF : fiche pré-consultation (export), export graphique, PDF synthétiques (gabarits de laboratoire). |
| `pdf-reading` | Inspecter des PDF d'entrée (natifs vs scannés), vérifier le rendu des documents synthétiques. |
| `docx` | Rapport technique de PFA et rapport d'évaluation au format Word si demandé. |
| `pptx` | Présentation de soutenance (si .pptx demandé ; sinon type Slides). |
| `xlsx` | Tableaux de résultats d'évaluation (métriques par champ, par pathologie) si export demandé. |
| `artifact-design` / `artifact-diagramming` | Diagrammes d'architecture et de flux de données (Figure 2), Gantt (Figure 3), maquettes publiées. |
| `skill-creator` | Optionnel : transformer les routines récurrentes (génération de dossiers, évaluation) en skills réutilisables. |
| `file-reading` | Lecture des fichiers fournis (CdC, jeux de données). |

### 1.2 Compétences techniques à mobiliser

- **Backend** : Python 3.11, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, JWT (python-jose/pyjwt), bcrypt, pytest, httpx.
- **Extraction documentaire** : pdfplumber/PyMuPDF (PDF natif), Tesseract `fra` ou PaddleOCR (scans), regex + règles prioritaires, LLM à sortie JSON contrainte, validation Pydantic.
- **LLM** : API Groq (modèles ouverts) avec anonymisation préalable, ou Ollama local ; prompts contraints ; few-shot.
- **Vision** : PyTorch, `torchxrayvision` (DenseNet121 pré-entraîné), Grad-CAM (`pytorch-grad-cam` ou implémentation maison), transfer learning, calibration de seuils, AUC par pathologie.
- **Séries temporelles** : régression linéaire robuste (Theil-Sen / Huber), variations absolue/relative, règles configurables.
- **RAG (P2)** : embeddings BGE-M3 ou multilingual-e5, ChromaDB, citations, requêtes structurées pour les valeurs.
- **Frontend** : React + TypeScript, Vite, Tailwind CSS, Recharts, React Query, zoom synchronisé d'images.
- **DevOps** : Docker, Docker Compose, Git/GitHub, GitHub Actions (lint + tests), MLflow (optionnel).
- **Data** : génération de données synthétiques (Faker + simulateur de trajectoires), dégradation d'images PDF (bruit, rotation).
- **Évaluation** : précision/rappel/F1, AUC, SUS, test chronométré, études d'ablation.
- **Éthique/légal** : loi marocaine 09-08, RGPD (minimisation, consentement, effacement), model card.

---

## 2. Architecture cible

### 2.1 Vue en couches

`présentation (React)` → `API (FastAPI)` → `moteurs d'analyse (tendances, imagerie, synthèse)` → `données (PostgreSQL, fichiers, base vectorielle)`

### 2.2 Flux de données

1. Dépôt PDF/scans/radios →
2. Texte/OCR + classification →
3. Extraction JSON + normalisation →
4. **Validation par le médecin** →
5. Base de suivi (séries temporelles) →
   - Moteur de tendances (pentes, variations, alertes par règles)
   - Moteur d'imagerie (scores IA, Grad-CAM, comparaison R(n)/R(n-1))
   - Frise traitements/événements
   - Assistant RAG (P2)
6. Tableau de bord du pneumologue : courbes 3 mois / 6 mois / 1 an, radios comparées, fiche pré-consultation, alertes.

### 2.3 Structure du dépôt (à créer en S1/S2)

```
medimind-ai/
├── README.md
├── docker-compose.yml
├── .env.example
├── .github/workflows/ci.yml
├── docs/
│   ├── CDC.pdf                      # cahier des charges validé
│   ├── DECISIONS.md                 # décisions d'architecture (ADR courtes)
│   ├── architecture.md              # + schémas (flux, composants)
│   ├── data-model.md                # schéma E/R
│   ├── uml/                         # cas d'usage, séquence, classes
│   ├── mockups/                     # 4 écrans clés
│   ├── model-card.md
│   └── evaluation-report.md
├── referential/
│   └── referentiel_clinique.yaml    # ~25 paramètres, unités, zones, règles
├── synthetic/
│   ├── generator/                   # générateur de dossiers synthétiques
│   ├── templates/                   # 3 gabarits de laboratoire (HTML→PDF)
│   ├── out/                         # dossiers générés (gitignored si lourd)
│   └── ground_truth/                # JSON de vérité terrain
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/ (config, security, logging)
│   │   ├── db/ (models, session, migrations)
│   │   ├── api/ (auth, patients, documents, measurements, timeline, imaging, alerts, summaries, chat, audit, jobs)
│   │   ├── services/
│   │   │   ├── ingestion/ (text_extract, ocr, classify, extract_llm, extract_rules, normalize, validate)
│   │   │   ├── trends/ (regression, qualify, alerts)
│   │   │   ├── imaging/ (preprocess, inference, gradcam, series)
│   │   │   ├── summary/ (facts, writer, verifier, pdf_render)
│   │   │   ├── anonymize/
│   │   │   └── rag/ (index, retrieve, answer)  # P2
│   │   └── schemas/ (Pydantic)
│   └── tests/
├── frontend/
│   └── src/ (pages, components, charts, viewer, api, hooks)
├── ml/
│   ├── notebooks/ (EDA ChestX-ray14, finetune, eval)
│   ├── scripts/ (select_patients.py, finetune.py, calibrate_thresholds.py)
│   └── weights/ (gitignored)
├── evaluation/
│   ├── questions_60.jsonl           # 60 questions cliniques annotées
│   ├── run_extraction_eval.py
│   ├── run_imaging_eval.py
│   ├── run_summary_eval.py
│   ├── run_rag_eval.py              # P2
│   └── chrono_test_protocol.md + sus_form.md
└── scripts/ (seed_demo.py, make_demo_patient.py)
```

---

## 3. Modèle de données (PostgreSQL)

| Entité | Attributs principaux |
|---|---|
| `users` | id, name, email, password_hash (bcrypt), role (`doctor`/`admin`) |
| `patients` | id, doctor_id, age, sex, antecedents, pack_years, allergies, base_treatments |
| `documents` | id, patient_id, type (`bilan_bio`/`efr`/`compte_rendu`/`ordonnance`/`radiographie`), exam_date, file_path, extracted_text, status, confidence |
| `parameters` (référentiel) | code, name, synonyms[], unit, ref_low, ref_high |
| `measurements` | id, patient_id, parameter_code, value, unit, date, source_document_id, confidence, validation_status (`pending`/`validated`/`corrected`/`rejected`) |
| `treatments` | id, patient_id, molecule, dosage, start_date, end_date, source_document_id |
| `clinical_events` | id, patient_id, type (`exacerbation`/`hospitalisation`/`treatment_change`/…), date, note |
| `imaging` | id, document_id, date, scores (JSONB par pathologie), gradcam_path, suggested_evolution, uncertainty, validation |
| `alerts` | id, patient_id, rule_id, source_values (JSONB), date, state |
| `consultation_sheets` | id, patient_id, date, facts (JSONB), text, verification (JSONB), pdf_path |
| `conversations` (P2) | id, user_id, patient_id, messages (JSONB), cited_sources (JSONB) |
| `audit_log` | id, user_id, action, object, timestamp |
| `jobs` | id, type, ref_id, status (`queued`/`running`/`done`/`failed`), error, created_at, finished_at |

Contraintes : isolation par patient (toute requête filtre par `doctor_id` + `patient_id`), index `(patient_id, parameter_code, date)`.

---

## 4. Référentiel clinique (`referentiel_clinique.yaml`)

À créer en S1, **à faire relire par un pneumologue** si possible. ~25 paramètres. Format cible :

```yaml
parameters:
  - code: FEV1
    name: VEMS
    synonyms: [VEMS, FEV1, "VEMS (L)", "FEV 1"]
    unit: L
    alt_units: {"mL": 0.001}
    plausible: [0.2, 6.0]
    reference: {low: null, high: null, note: "% prédit selon âge/sexe/taille"}
  - code: FVC
    name: CVF
    synonyms: [CVF, FVC]
    unit: L
    plausible: [0.5, 8.0]
  - code: FEV1_FVC
    name: Rapport VEMS/CVF
    synonyms: ["VEMS/CVF", "Tiffeneau", "FEV1/FVC"]
    unit: ratio
    plausible: [0.2, 1.0]
  - code: FVC_PRED
    name: CVF (% prédit)
    unit: "%"
  - code: DLCO
    name: DLCO (% prédit)
    unit: "%"
  - code: SPO2
    name: SpO2
    synonyms: [SpO2, "Sat O2", "Saturation"]
    unit: "%"
    reference: {low: 95, high: 100}
  - code: CRP
    name: CRP
    synonyms: [CRP, "Protéine C réactive"]
    unit: mg/L
    reference: {low: 0, high: 5}
  - code: WBC
    name: Leucocytes
    synonyms: [Leucocytes, GB, WBC]
    unit: "G/L"
    reference: {low: 4, high: 10}
  - code: EOS
    name: Éosinophiles
    unit: "G/L"
    reference: {low: 0, high: 0.5}
  # À compléter : PNN, lymphocytes, Hb, plaquettes, créatinine, urée, glycémie, PCT,
  # fibrinogène, D-dimères, pH, PaO2, PaCO2, HCO3, LDH, NT-proBNP, IgE (≈ 25 au total)

alert_rules:
  - id: GOLD_FEV1_FVC_070
    description: "Rapport VEMS/CVF < 0,70 (critère GOLD, à valider)"
    when: {param: FEV1_FVC, op: "<", value: 0.70}
  - id: CRP_HIGH
    description: "CRP supérieure à la borne haute"
    when: {param: CRP, op: ">", value: 5}
  - id: ILD_FVC_DROP
    description: "Progression : baisse absolue de la CVF ≥ 5 % du prédit sur 1 an (ATS/ERS/JRS/ALAT 2022)"
    when: {param: FVC_PRED, window_days: 365, delta_abs: -5}
  - id: ILD_DLCO_DROP
    description: "Baisse absolue de la DLCO ≥ 10 % sur 1 an"
    when: {param: DLCO, window_days: 365, delta_abs: -10}
  - id: SPO2_LOW
    description: "SpO2 < 92 %"
    when: {param: SPO2, op: "<", value: 92}

trend_qualification:
  min_points: 3
  stable_band_rel: 0.05     # |variation relative| < 5 % → stable
```

Chaque alerte **cite la règle et les valeurs sources**.

---

## 5. Jeux de données

### 5.1 Radiographies (réelles, publiques)
- **NIH ChestX-ray14** : 112 120 images, 30 805 patients ; 13 302 patients ont plus d'une radio. Les métadonnées contiennent l'ID patient et le numéro de suivi (`Follow-up #`).
- Script `ml/scripts/select_patients.py` : sélectionner des patients avec **≥ 3 radiographies** et étiquettes d'intérêt (Infiltration, Pneumonia, Consolidation, Effusion, Atelectasis, Emphysema, Fibrosis, Cardiomegaly…). Attribuer des **dates synthétiques** selon le numéro de suivi.
- Attribution : citer Wang et al., CVPR 2017 et mentionner le NIH Clinical Center.
- Option : MIMIC-CXR (accès PhysioNet sur demande préalable) ; ne pas en dépendre.

### 5.2 Dossiers synthétiques (générateur à écrire)
- 36 patients (**12 par parcours**), 4 à 8 visites chacun.
- Parcours : **A. BPCO avec exacerbations** ; **B. Pneumonie et résolution** ; **C. Fibrose pulmonaire progressive**.
- Pour chaque patient : trajectoires simulées (VEMS, CVF, rapport, SpO2, CRP, leucocytes, éosinophiles, DLCO…), événements (exacerbation, hospitalisation, changement de traitement), ordonnances, comptes rendus, EFR.
- **3 gabarits de laboratoire différents** (mise en page, noms de paramètres, unités) rendus en PDF (HTML → PDF via WeasyPrint/Playwright). Une partie des PDF est **dégradée en scans** (bruit, rotation, flou, JPEG) pour tester l'OCR.
- **Vérité terrain** : JSON écrit par construction (`synthetic/ground_truth/{patient_id}.json`) avec paramètre, valeur, unité, date.
- Alignement : les trajectoires de biologie suivent les étiquettes de la radiographie du patient (limite assumée : cohérence clinique non réelle, à documenter).
- Partition : **30 patients développement, 6 patients de test jamais utilisés** pendant la mise au point (fichier `splits.json` figé).

### 5.3 Évaluation
- `evaluation/questions_60.jsonl` : 60 questions cliniques annotées (ex. « quel était le VEMS il y a 6 mois ? », « la CRP a-t-elle normalisé après l'antibiotique ? ») avec réponse attendue calculée depuis la vérité terrain.

---

## 6. Planning détaillé par semaine

> Pour chaque semaine : **objectifs → tâches → livrable → critères d'acceptation**. L'agent doit cocher les cases dans `docs/PROGRESS.md` et ne pas passer à la semaine suivante sans avoir validé les critères (sauf règle de coupe).

### Semaine 1 : Cadrage, référentiel, maquettes
**Tâches**
- [ ] Créer le dépôt Git, structure du §2.3, README initial, `.gitignore`, `.env.example`, licence/mentions de données.
- [ ] `docs/DECISIONS.md` : stack figée (voir §1.2).
- [ ] Rédiger les user stories du pneumologue (au moins 15) et les diagrammes de cas d'usage (`docs/uml/`).
- [ ] Rédiger `referentiel_clinique.yaml` (v0) : paramètres, synonymes, unités, zones de référence, règles d'alerte (§4).
- [ ] Préparer le **guide d'entretien (30 min)** avec un pneumologue + questionnaire écrit en plan B (`docs/interview_guide.md`, `docs/questionnaire_plan_b.md`).
- [ ] Maquettes des **4 écrans clés** : (1) écran d'évolution (courbes + événements + alertes), (2) comparateur de radiographies, (3) écran de validation (valeur vs document source), (4) fiche pré-consultation. Skills : `frontend-design`, `dataviz`.
- [ ] Backlog priorisé P1/P2/P3 (issues GitHub ou `docs/BACKLOG.md`) avec IDs F-A1…F-E5.
**Livrable** : CdC validé, maquettes, backlog.
**Acceptation** : maquettes couvrent les 4 écrans ; backlog contient toutes les fonctionnalités F-xx avec priorité ; référentiel parse sans erreur (test unitaire de schéma YAML).

### Semaine 2 : Données synthétiques et socle déployable
**Tâches**
- [ ] `synthetic/generator` : simulateur de trajectoires par parcours (A/B/C), événements, ordonnances, comptes rendus, EFR.
- [ ] 3 gabarits de laboratoire (HTML→PDF), pipeline de dégradation en scans, vérité terrain JSON, `splits.json` (30/6).
- [ ] `ml/scripts/select_patients.py` + téléchargement/index des métadonnées ChestX-ray14 ; sélection des séries ≥ 3 radios ; dates synthétiques.
- [ ] Socle backend : FastAPI, config, SQLAlchemy + Alembic, modèles du §3, `/health`.
- [ ] **Authentification JWT + rôles (F-A1)** : register/login/refresh, hash bcrypt, dépendances `require_role`, isolation par patient.
- [ ] Socle frontend : Vite + React + TS + Tailwind, routing, client API, page login.
- [ ] `docker-compose.yml` : `db` (PostgreSQL), `backend`, `frontend`, volume `storage`. `make up` démarre tout.
- [ ] CI GitHub Actions : lint (ruff, eslint), pytest, build frontend.
**Livrable** : jeux de données, socle déployable.
**Acceptation** : `docker compose up` ⇒ login fonctionnel ; 36 patients générés avec vérité terrain ; 3 gabarits visuellement différents ; CI verte.

### Semaine 3 : Module A (ingestion et normalisation)
**Tâches**
- [ ] **F-A2** Fiche patient (âge, sexe, antécédents, paquets-années, allergies, traitements de fond) : API CRUD + formulaire.
- [ ] **F-A3** Téléversement multi-fichiers (PDF/JPG/PNG) avec date de l'examen ; stockage sur volume ; création d'un `job`.
- [ ] **F-A4** Extraction de texte : PDF natif (pdfplumber/PyMuPDF) ; scans : prétraitement + OCR (Tesseract `fra` ou PaddleOCR) ; **score de confiance par ligne**.
- [ ] **F-A5** Classification du document (règles + LLM few-shot) : bilan biologique, EFR, compte rendu, ordonnance, radiographie.
- [ ] **F-A6** Extraction structurée en JSON validée par Pydantic : `{parameter, value, unit, date, confidence}`. Tableaux de laboratoire traités **par règles en priorité** ; LLM à sortie contrainte pour le reste. Brancher l'**anonymisation** avant tout appel LLM externe (`services/anonymize`).
- [ ] **F-A7** Normalisation : dictionnaire de synonymes (VEMS = FEV1, CVF = FVC…), conversion d'unités (ex. g/dL ↔ g/L), dédoublonnage, contrôle de plausibilité.
- [ ] **F-A8** **Écran de validation** : valeur extraite en regard du document source (surbrillance de la zone), correction en un clic, statut validé/corrigé/rejeté.
- [ ] **F-A9 (P2)** Journal d'audit des accès et corrections.
- [ ] Endpoint d'état des jobs (traitement asynchrone consultable, reprise sur échec).
- [ ] Premier script d'évaluation d'extraction (`run_extraction_eval.py`) sur les patients de dev.
**Livrable** : Module A.
**Acceptation** : sur les patients de dev, F1 d'extraction ≥ 0,90 (PDF natifs) ; traitement d'un document < 30 s ; l'écran de validation permet de corriger et d'écrire la mesure horodatée en base ; tests unitaires sur normalisation et conversion d'unités.

### Semaine 4 : Modules B et D (courbes, événements, traitements, alertes)
**Tâches**
- [ ] **F-D1** Extraction des traitements depuis les ordonnances (molécule, posologie, dates) → table `treatments`.
- [ ] Gestion des événements cliniques (exacerbation, hospitalisation, changement de traitement) : CRUD + extraction depuis comptes rendus.
- [ ] **API de séries temporelles** : `GET /patients/{id}/series?params=...&from=...&to=...` (données validées uniquement).
- [ ] **F-B1** Sélecteur de période : 3 mois, 6 mois, 1 an, tout l'historique, dates personnalisées.
- [ ] **F-B2** Courbes interactives multi-paramètres (Recharts) avec **zones de référence** et valeurs hors normes mises en évidence. Skill : `dataviz`.
- [ ] **F-B3** Annotation automatique des événements sur les courbes (début/changement de traitement, exacerbation, hospitalisation, radiographie).
- [ ] **F-D2** Frise des traitements et événements superposable aux courbes.
- [ ] **F-B4** Tendance : pente (régression linéaire robuste), variation absolue et relative entre deux dates, qualification « stable / amélioration / dégradation » selon règles configurables (`trend_qualification`).
- [ ] **F-B5** Alertes cliniques par règles du référentiel, **avec explication et valeurs sources** (ex. critère de progression de la CVF).
- [ ] Tests unitaires : cas de référence pour tendances et alertes (**100 % de concordance** exigée).
**Livrable** : Modules B et D (P1).
**Acceptation** : affichage des courbes 1 an < 2 s ; pour les parcours A, B, C : les alertes attendues se déclenchent avec la bonne règle citée ; la frise s'aligne sur les courbes.

### Semaine 5 : Module C (imagerie) et **jalon MVP**
**Tâches**
- [ ] **F-C1** Liste chronologique des radiographies du patient (R1…Rn), ingestion PNG/JPG, date d'examen.
- [ ] **F-C2** Inférence : prétraitement TorchXRayVision, DenseNet121 pré-entraîné, **probabilités par pathologie** ; affinage (transfer learning) sur les pathologies d'intérêt si le temps le permet (`ml/scripts/finetune.py`). Inférence < 5 s.
- [ ] **F-C3** Carte de chaleur **Grad-CAM** par radiographie ; incertitude estimée par augmentation à l'inférence (TTA).
- [ ] **F-C4** **Visionneuse comparative** : R(n) contre R(n-1) ou deux radios au choix, **zoom synchronisé**, curseur de superposition. Skill : `frontend-design`.
- [ ] **F-C5** **Courbe des scores IA** par pathologie dans le temps, **alignée sur les courbes biologiques** (même axe temporel).
- [ ] Intégration au tableau de bord unique (courbes + radios + alertes).
- [ ] Mesure de base de l'AUC sur les séries de dev ; calibration du seuil d'évolution (`calibrate_thresholds.py`).
- [ ] Préparer le **scénario de démo parcours A** (patient BPCO fictif sur 12 mois).
- [ ] **E2E MVP** : dépôt de documents → extraction et normalisation → validation par le médecin → courbes 3m/6m/1an avec événements et alertes (F-B1…B5) → analyse et comparaison de radiographies (F-C1…C5) → **fiche pré-consultation minimale** (version simple : faits + gabarit, sans LLM si besoin).
**Livrable** : MVP.
**Acceptation (jalon MVP)** : toutes les fonctionnalités **P1** démontrables sur le parcours A, de bout en bout, en direct ; démonstration intermédiaire à l'encadrant.
**Revue de périmètre à la fin de S5** : si retard, appliquer la **règle de coupe**.

### Semaine 6 : Module E (synthèse) et P2
**Tâches**
- [ ] **F-E1 / F-E2** Pipeline fiche pré-consultation :
  1. Calcul par code d'un dossier de **faits** (dernières valeurs, variations, alertes, traitements, radiographies comparées) → `facts` JSON.
  2. Rédaction par le LLM **à partir de ces seuls faits** (prompt contraint, sortie structurée).
  3. **Vérificateur** : extraire tous les nombres et dates du texte, vérifier qu'ils existent dans les faits ; sinon régénérer (max N essais) puis signaler.
  4. Mise en page **PDF d'une page** (motif, évolution depuis la dernière visite, alertes, radiographies comparées, traitements en cours, points à aborder) avec renvois vers les documents sources. Skill : `pdf`.
- [ ] **F-E3** Garde-fous : refus hors dossier, avertissement « aide à la décision ».
- [ ] **F-B6 (P2)** Tableau « dernière valeur / précédente / variation ». **F-B7 (P2)** Export PDF/PNG du graphique.
- [ ] **F-C6 (P2)** Évolution suggérée « stable / amélioration / aggravation » avec indicateur d'incertitude, **validée par le médecin** ; **F-C7 (P2)** annotation sur la radiographie.
- [ ] **F-E4 (P2)** Assistant RAG sur le dossier : indexation (BGE-M3/multilingual-e5 + ChromaDB), citations, **valeurs et dates lues par requête structurée** (jamais par génération libre).
- [ ] Renforcer l'anonymisation (nom, identifiant, téléphone) avant tout appel externe ; test dédié.
- [ ] (P3 si temps) F-B8 comparaison de deux périodes ; F-D3 interactions médicamenteuses ; F-E5 brouillon de compte rendu ; F-C8 recalage + carte de différence.
**Livrable** : Module E.
**Acceptation** : génération de la fiche < 20 s ; **100 % des nombres du texte retrouvés dans les faits** après vérificateur ; export PDF correct ; test d'anonymisation passe.

### Semaine 7 : Sécurité, tests, évaluation, gel
**Tâches**
- [ ] **Sécurité** : TLS (proxy/compose), mots de passe bcrypt, JWT à expiration, contrôle d'accès par rôle, isolation par patient (tests d'accès croisé), journal d'accès, chiffrement au repos du volume si possible.
- [ ] **Tests** : unitaires (règles cliniques, normalisation, vérificateur), intégration (pipeline complet), performance (budgets du §8), e2e (Playwright) sur le parcours A.
- [ ] **Docker Compose final** : un seul `docker compose up` ; documentation d'installation ; seed de démo (`scripts/seed_demo.py`).
- [ ] **Campagne d'évaluation** sur les 6 patients de test (jamais utilisés) :
  - Extraction : P/R/F1 par champ (cibles : **F1 ≥ 0,95 PDF natifs, ≥ 0,85 scans**).
  - Normalisation ≥ 95 %. Tendances/alertes : 100 % des cas de référence.
  - Imagerie : AUC par pathologie, **test séparé au niveau patient**, poids pré-entraînés sur d'autres jeux que celui du test (cibles : **AUC moyenne ≥ 0,80, ≥ 0,75 par pathologie retenue** ; ≥ 70 % de séries d'évolution concordantes).
  - Fiche : 100 % des nombres vérifiés.
  - RAG (P2) : fidélité aux sources et citation correcte ≥ 85 % sur les 60 questions.
- [ ] **Ablations** : (i) fiche LLM seul vs LLM + faits calculés + vérificateur ; (ii) extraction règles seules vs LLM seul vs hybride.
- [ ] **Test chronométré** (5 questions cliniques, avec/sans l'outil, objectif **−50 % de temps**) et **score SUS ≥ 75** avec un clinicien (ou proxy encadrant) ; documenter le retour.
- [ ] Analyse par âge et par sexe ; rédiger `docs/model-card.md` (données, performances, limites).
- [ ] **Gel des fonctionnalités** en fin de S7.
**Livrable** : rapport d'évaluation, application finale.
**Acceptation** : au moins **80 % des métriques cibles** atteintes (sinon documenter l'écart et ses causes) ; budgets de performance respectés (courbes < 2 s ; document < 30 s ; radio < 5 s ; fiche < 20 s).

### Semaine 8 : Finalisation (semaine tampon)
**Tâches**
- [ ] Corrections de bugs, refactoring léger, nettoyage du dépôt, README final et guide d'installation.
- [ ] **Rapport final** (structure : contexte, état de l'art, conception, implémentation, évaluation, éthique, limites, perspectives). Skill : `docx` si Word demandé.
- [ ] **Vidéo de démonstration** (parcours A, 12 mois : dépôt → validation → courbes 6 mois/1 an → comparaison radios → fiche).
- [ ] **Présentation de soutenance** (skill `pptx` ou type Slides).
- [ ] Vérifier la **reproductibilité** : clone propre → `docker compose up` → seed → démo.
**Livrable** : rapport, démo, présentation.
**Acceptation** : tous les livrables du §8 présents ; critères de réussite du §9 satisfaits.

---

## 7. Spécifications fonctionnelles de référence (checklist)

| Réf. | Fonctionnalité | Prio. |
|---|---|---|
| F-A1 | Authentification JWT, rôles (médecin, administrateur), contrôle d'accès | P1 |
| F-A2 | Fiche patient (âge, sexe, antécédents, tabagisme, allergies, traitements de fond) | P1 |
| F-A3 | Téléversement multi-fichiers (PDF, JPG, PNG) avec date de l'examen | P1 |
| F-A4 | Extraction texte (PDF natif) et OCR (scans) avec score de confiance | P1 |
| F-A5 | Classification du document | P1 |
| F-A6 | Extraction structurée JSON (validation Pydantic) | P1 |
| F-A7 | Normalisation (synonymes, unités, dédoublonnage) | P1 |
| F-A8 | Écran de validation (valeur vs source, correction en un clic) | P1 |
| F-A9 | Journal d'audit des accès et corrections | P2 |
| F-B1 | Sélecteur de période | P1 |
| F-B2 | Courbes interactives multi-paramètres + zones de référence | P1 |
| F-B3 | Annotation automatique des événements | P1 |
| F-B4 | Tendance, variation, qualification configurable | P1 |
| F-B5 | Alertes cliniques par règles, expliquées | P1 |
| F-B6 | Tableau dernière valeur / précédente / variation | P2 |
| F-B7 | Export PDF/PNG du graphique | P2 |
| F-B8 | Comparaison de deux périodes | P3 |
| F-C1 | Liste chronologique des radiographies | P1 |
| F-C2 | Analyse IA par radiographie (probabilités par pathologie) | P1 |
| F-C3 | Carte de chaleur Grad-CAM | P1 |
| F-C4 | Visionneuse comparative (zoom synchronisé, superposition) | P1 |
| F-C5 | Courbe des scores IA alignée sur la biologie | P1 |
| F-C6 | Évolution suggérée avec incertitude, validée par le médecin | P2 |
| F-C7 | Annotation par le médecin sur la radiographie | P2 |
| F-C8 | Recalage automatique + carte de différence | P3 |
| F-D1 | Extraction des traitements depuis les ordonnances | P1 |
| F-D2 | Frise traitements/événements superposable | P1 |
| F-D3 | Alerte interactions et contre-indications (règles limitées) | P3 |
| F-E1 | Fiche pré-consultation d'une page | P1 |
| F-E2 | Chiffres déterministes + vérificateur | P1 |
| F-E3 | Garde-fous (hors dossier, avertissement) | P1 |
| F-E4 | Assistant conversationnel RAG avec citations | P2 |
| F-E5 | Brouillon de compte rendu modifiable | P3 |

---

## 8. Exigences non fonctionnelles et livrables

**Budgets** : courbes d'un patient (1 an) < 2 s ; document < 30 s ; inférence radio < 5 s ; fiche < 20 s.
**Sécurité** : TLS, bcrypt, JWT, contrôle d'accès par rôle, isolation par patient. **Confidentialité** : données synthétiques/publiques, anonymisation avant LLM externe, journal d'accès. **Fiabilité** : gestion d'erreurs, jobs consultables, reprise sur échec. **Explicabilité** : source de chaque valeur, Grad-CAM, scores, incertitude. **Ergonomie** : français, responsive, écran unique de suivi. **Maintenabilité** : code modulaire versionné, tests unitaires sur règles cliniques et normalisation, Docker Compose.

**Livrables finaux**
1. Cahier des charges (`docs/CDC.pdf`).
2. Maquettes et dossier de conception (architecture, UML, modèle de données).
3. Code source commenté sur Git, README et guide d'installation.
4. Application déployable par Docker Compose.
5. Générateur de données synthétiques, jeux de données et référentiel clinique.
6. Notebooks d'évaluation et rapport d'évaluation (métriques, ablations, limites).
7. Rapport final, présentation de soutenance, vidéo de démonstration.

---

## 9. Critères de réussite globaux

- Démo en direct sur un patient BPCO suivi 12 mois : dépôt de documents et radios → validation → courbes 6 mois et 1 an → comparaison de radios → fiche pré-consultation.
- Toutes les P1 livrées ; au moins la moitié des P2.
- Au moins 80 % des métriques cibles atteintes.
- Gain de temps mesuré (−50 %) et retour d'un clinicien documenté (SUS ≥ 75).
- Projet reproductible et documenté.

---

## 10. Prompts système de référence (à adapter)

**Classification (few-shot)** : « Tu classes un document médical en : bilan_bio, efr, compte_rendu, ordonnance, radiographie. Réponds uniquement par JSON `{"type": "...", "confidence": 0-1}`. »

**Extraction contrainte** : « Extrais uniquement ce qui est explicitement écrit. Sortie JSON conforme au schéma fourni. Si une valeur est absente, omets-la. N'invente jamais de valeur, d'unité ni de date. »

**Rédaction de la fiche** : « Tu rédiges une synthèse de consultation pour un pneumologue **uniquement à partir du JSON de faits fourni**. N'ajoute aucun nombre, date ou fait absent. Style télégraphique, français médical. Termine par l'avertissement : *aide à la décision, aucun diagnostic*. »

**Assistant RAG (P2)** : « Réponds uniquement avec les extraits fournis, cite chaque source (document, date). Pour toute valeur ou date, utilise le résultat de la requête structurée. Si l'information n'est pas dans le dossier, refuse. »

---

## 11. Gestion des risques (à surveiller par l'agent)

| Risque | Impact | Mesure |
|---|---|---|
| Périmètre trop large pour 8 semaines | Élevé | MVP en S5, priorités, règle de coupe |
| Évolution radiologique difficile à valider | Élevé | Fonction P2 présentée comme aide, évaluation sur séries étiquetées, aucun diagnostic |
| Radios réelles + biologie synthétique | Moyen | Générateur aligné sur les étiquettes, limite documentée |
| Pas d'accès à un clinicien | Moyen | Via l'encadrant dès S1 ; plan B : GOLD/ATS-ERS + questionnaire écrit |
| Qualité OCR sur scans | Moyen | PDF natifs prioritaires, plusieurs moteurs, validation humaine |
| Hallucinations du LLM | Élevé | Faits calculés, vérificateur, citations |
| Calcul limité | Moyen | Modèles pré-entraînés, affinage optionnel Colab/Kaggle |
| Retard d'intégration | Moyen | CI, démo toutes les 2 semaines |

---

## 12. Rituels et communication

- **Point hebdomadaire** avec l'encadrant ; **démonstration intermédiaire toutes les deux semaines** (fins de S2, S4, S6, S8).
- À la fin de chaque semaine : mettre à jour `docs/PROGRESS.md` (fait / reste / blocages / décisions) et ouvrir une release/tag (`v0.S`).
- Répartition indicative : **Ishak** = modules A, B, D, E, backend, BDD, sécurité, Docker ; **Ismail** = module C (imagerie), frontend, expérience utilisateur ; **partagé** = données synthétiques, évaluation, tests utilisateurs, rapport, soutenance ; revues de code croisées.

---

## 13. Références

- Wang et al., *ChestX-ray8: Hospital-scale Chest X-ray Database and Benchmarks*, CVPR 2017 (NIH ChestX-ray14).
- Cohen et al., *TorchXRayVision: A library of chest X-ray datasets and models*, 2022 (arXiv:2111.00595).
- Oakden-Rayner, *Exploring large scale public medical image datasets*, 2019 (arXiv:1907.12720).
- Selvaraju et al., *Grad-CAM: Visual Explanations from Deep Networks*, 2017.
- Raghu et al., *IPF (an update) and Progressive Pulmonary Fibrosis in Adults: ATS/ERS/JRS/ALAT Clinical Practice Guideline*, AJRCCM 2022;205(9):e18–e47.
- GOLD, *Global Strategy for the Diagnosis, Management and Prevention of COPD* (rapport annuel).
- Lewis et al., *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*, 2020.
- Loi n° 09-08 (Maroc) relative à la protection des données à caractère personnel.

---

## 14. Définition de « terminé » (Definition of Done)

Une tâche est terminée quand : le code est mergé sur `main` ; les tests passent en CI ; la fonctionnalité est démontrable dans l'UI ; la documentation courte est à jour ; aucun secret ni donnée réelle n'est committé ; l'avertissement « aide à la décision » est présent sur tout résultat IA.

**Premier ordre pour l'agent** : lire ce fichier en entier, créer le dépôt (§2.3), écrire `docs/PROGRESS.md` avec les cases de la Semaine 1, puis démarrer la Semaine 1.
