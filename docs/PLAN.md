# MediMind AI : plan de projet

> **Statut** : v1.0, novembre 2026. Remplace `MEDIMIND_AGENT_PLAN.md` comme référence de travail. Le cahier des charges (`Cahier_des_charges_PFA_MediMind_AI.pdf`) reste le document contractuel ; les écarts sont listés au §13.
> **Projet** : PFA 5IIR IA & Data, EMSI Casablanca, Groupe 3. Étudiants : Lamzouri Ishak, Amrani Ismail. Encadrant : Pr Adil Chergui.
> **Statut** : fonctionnalités, règles et seuils **validés par l'encadrant le 2026-11-11**. Toute modification passe par `docs/DECISIONS.md`.

---

## 1. Destination d'usage (intended use)

MediMind AI est une **application web d'aide à la décision** destinée aux **pneumologues** qui suivent des **patients adultes (≥ 18 ans)** atteints de BPCO, de fibrose pulmonaire ou en convalescence de pneumonie. Elle reconstitue l'historique du patient à partir de documents hétérogènes (bilans, EFR, comptes rendus, ordonnances, radiographies) et en présente l'évolution de façon **vérifiable**.

- Elle **n'établit aucun diagnostic** et ne propose aucun traitement. Le médecin valide toute valeur et toute sortie IA.
- **Statut** : démonstrateur de recherche (PFA), **non dispositif médical**, données publiques ou synthétiques uniquement. La commercialisation éventuelle est traitée au §12.

## 2. Périmètre

| Inclus | Exclu |
|---|---|
| Pneumologue (+ administrateur technique sans accès aux données patient) | Patients < 18 ans (refus à la saisie) |
| Parcours A (BPCO + exacerbations), B (pneumonie + résolution), C (fibrose progressive) | Asthme, tuberculose, cancer, scanner 3D |
| Ingestion PDF/JPG/PNG, courbes, frise, imagerie comparée, fiche pré-consultation | Diagnostic, prescription, interactions médicamenteuses (F-D3 retirée) |
| LLM local (Ollama) | Tout LLM ou service externe recevant des données patient |
| Données publiques (NIH, RSNA) + synthétiques | Données réelles, connexion SIH/PACS, FHIR |

---

## 3. Fonctionnalités par module

**Tranches (ordre de construction, tout est construit)** : **T1** socle et chaîne démontrable de bout en bout · **T2** reste des P1 du CdC · **T3** P2/P3 retenues.

### Module 0 : Socle

| ID | Fonctionnalité | Dépend de | Tranche | Acceptation |
|---|---|---|---|---|
| F-01 | Référentiel `referentiel_clinique.yaml` (≈ 20 paramètres, synonymes, unités, bornes, règles sourcées, `version`) | — | T1 | Test de schéma YAML ; chaque règle a un champ `source` |
| F-02 | Générateur synthétique (§6.2) + vérité terrain JSON + `splits.json` figé | F-01 | T1 | 36 patients, 4 gabarits, PDF natifs + scans dégradés |
| F-A1 | Auth JWT (access + refresh), bcrypt, rôles `doctor` / `admin` ; isolation par médecin et par patient | — | T1 | Tests d'accès croisé : un médecin ne voit jamais le patient d'un autre ; `admin` n'accède à aucune donnée patient |
| F-03 | Table `jobs` (BackgroundTasks FastAPI), état consultable, relance sur échec | — | T1 | Un job en échec est rejouable |
| F-A9 | Journal d'audit (lecture, correction, génération IA) | F-A1 | T1 | Toute action sur un patient est tracée |

### Module A : Dossier patient et ingestion

| ID | Fonctionnalité | Dépend de | Tranche | Acceptation |
|---|---|---|---|---|
| F-A2 | Fiche patient (date de naissance, sexe, taille, antécédents, paquets-années, allergies, traitements de fond) ; **refus si < 18 ans** | F-A1 | T1 | Validation Pydantic, test < 18 ans |
| F-A3 | Téléversement multi-fichiers + date d'examen ; hash SHA-256 (dédoublonnage) ; crée un job | F-03 | T1 | Doublon détecté |
| F-A4 | Texte : PDF natif (PyMuPDF) ; scans : prétraitement (redressement, binarisation) + Tesseract `fra` ; **confiance par ligne + boîtes englobantes** | F-A3 | T1 | Boîtes réutilisées par F-A8 |
| F-A5 | Classification du document : **règles (mots-clés) d'abord**, LLM local en repli | F-A4 | T1 | ≥ 95 % sur le jeu de dev |
| F-A6 | Extraction structurée `{parameter, value, unit, date, context, confidence, bbox}` : **parseurs de tableaux/regex d'abord**, LLM local à sortie JSON contrainte en repli ; validation Pydantic | F-A5, F-01 | T1 | Aucune valeur sans `bbox` ni texte source |
| F-A7 | Normalisation : synonymes, conversion d'unités, ratio vs %, **contexte de mesure** (pré/post-bronchodilatateur, repos/effort, air/O₂), plausibilité, dédoublonnage | F-01 | T1 | Tests unitaires par paramètre et par unité |
| F-A8 | Écran de validation : valeur ↔ zone surlignée du document, corriger / valider / rejeter en un clic | F-A4, F-A6 | T1 | Mesure écrite en base avec statut et auteur |

### Module B : Évolution des paramètres

| ID | Fonctionnalité | Dépend de | Tranche | Acceptation |
|---|---|---|---|---|
| F-B1 | Sélecteur de période (3 m, 6 m, 1 an, tout, personnalisé) | F-A8 | T1 | — |
| F-B2 | Courbes multi-paramètres (Recharts), zones de référence, hors-normes mis en évidence ; **mesures validées uniquement** (non validées affichées à part, marquées) | F-A8 | T1 | 1 an affiché < 2 s |
| F-B4 | Tendance : pente Theil-Sen (≥ 3 points), variation absolue et relative ; qualification par **seuils absolus propres à chaque paramètre** (ex. VEMS ± 100 mL) | F-01 | T2 | 100 % des cas de référence |
| F-B5 | Alertes par règles : règle citée + source bibliographique + valeurs déclenchantes + `ruleset_version` ; **acquittement** par le médecin | F-B4 | T2 | Parcours A, B, C : alertes attendues et seulement elles |
| F-B3 | Annotation automatique des événements (traitement, exacerbation, hospitalisation, radio) | F-D1, F-D4 | T2 | — |
| F-B6 | Tableau dernière / précédente / variation | F-B4 | T3 | — |
| F-B7 | Export PNG/PDF du graphique | F-B2 | T3 | — |
| F-B8 | Comparaison de deux périodes | F-B4 | T3 | — |

### Module C : Imagerie thoracique

| ID | Fonctionnalité | Dépend de | Tranche | Acceptation |
|---|---|---|---|---|
| F-C1 | Liste chronologique R1…Rn ; contrôle de vue (face PA/AP) et de qualité ; refus hors distribution | F-A3 | T1 | Image latérale ou illisible signalée |
| F-C2 | Scores par pathologie, TorchXRayVision `densenet121-res224-all`, CPU ; **nom et version du modèle stockés** | F-C1 | T1 | < 5 s par image sur CPU |
| F-C3 | Grad-CAM, légendé « zone d'attention du modèle, pas une localisation de lésion » ; incertitude par augmentation à l'inférence | F-C2 | T2 | — |
| F-C4 | Visionneuse comparative R(n) / R(n-1) ou au choix : zoom et déplacement synchronisés, curseur de superposition | F-C1 | T2 | — |
| F-C5 | Courbe des scores IA dans le temps, même axe que la biologie | F-C2, F-B2 | T2 | — |
| F-C6 | **Variation des scores entre deux radios** + intervalle d'incertitude ; le médecin qualifie lui-même l'évolution | F-C3, F-C5 | T3 | Pas de libellé « amélioration / aggravation » produit par l'IA |
| F-C7 | Annotation du médecin sur la radio | F-C4 | T3 | — |
| F-C8 | Recalage + carte de différence | F-C4 | T3 | Optionnel |

### Module D : Traitements et événements

| ID | Fonctionnalité | Dépend de | Tranche | Acceptation |
|---|---|---|---|---|
| F-D1 | Extraction des ordonnances : molécule (DCI), posologie, dates ; validée via F-A8 | F-A6 | T2 | — |
| F-D4 | Événements cliniques (exacerbation, hospitalisation, changement de traitement) : saisie manuelle + extraction des comptes rendus | F-A6 | T2 | — |
| F-D2 | Frise traitements/événements superposée aux courbes | F-D1, F-D4, F-B2 | T2 | Alignement temporel exact |

### Module E : Synthèse

| ID | Fonctionnalité | Dépend de | Tranche | Acceptation |
|---|---|---|---|---|
| F-E1 | Fiche pré-consultation 1 page (PDF) : motif, évolution, alertes, radios comparées, traitements, points à aborder, renvois aux sources | B, C, D | T2 | — |
| F-E2 | Pipeline **faits calculés par code → gabarit déterministe (par défaut)** → reformulation LLM locale optionnelle → **vérificateur** (chaque nombre/date ∈ faits ; 2 échecs ⇒ retour au gabarit) | F-E1 | T2 | 100 % des nombres vérifiés |
| F-E3 | Garde-fous : refus hors dossier, bandeau « aide à la décision » | F-E2 | T2 | — |
| F-E4 | Assistant RAG avec citations ; valeurs et dates lues par requête SQL, jamais générées | F-E2 | T3 | ≥ 85 % de citations correctes |

**Retirées** : F-D3 (interactions médicamenteuses : hors fil conducteur, dangereuse sans relecture clinique), F-E5 (brouillon de compte rendu).

### Graphe de dépendances (résumé)

```
F-01 référentiel ─┬─> F-02 générateur ──> (évaluation A)
                  └─> F-A7 normalisation
F-A1 auth ─> F-A2 patient ─> F-A3 upload ─> F-A4 OCR ─> F-A5 ─> F-A6 ─> F-A8 validation
F-A8 ─> F-B1/B2 courbes ─> F-B4 tendance ─> F-B5 alertes
F-A6 ─> F-D1/D4 ─> F-D2 frise, F-B3 annotations
F-A3 ─> F-C1 ─> F-C2 scores ─> F-C3, F-C5 ─> F-C6
B + C + D ─> F-E1/E2 fiche ─> F-E3 ─> F-E4 RAG
```

---

## 4. Garde-fous IA

1. **Validation humaine obligatoire** : courbes, tendances, alertes et fiches n'utilisent que les mesures `validated` / `corrected`.
2. **Aucun nombre généré** : tout chiffre affiché vient de la base ; le LLM ne fait que reformuler ; vérificateur systématique.
3. **Traçabilité de chaque sortie IA** : version du modèle, version du référentiel, document source, auteur de la validation, horodatage (journal d'audit).
4. **Règles avant LLM** pour la classification et l'extraction ; le LLM n'est qu'un repli, avec une confiance affichée.
5. **LLM 100 % local** (Ollama) ; aucune donnée patient ne quitte la machine. Le module d'anonymisation reste en place, par défense en profondeur.
6. **Imagerie** : scores présentés comme « probabilité estimée par un modèle de recherche », incertitude visible, Grad-CAM légendé, refus des vues non frontales, des images illisibles et des patients < 18 ans.
7. **Alertes** : chaque alerte cite sa règle et sa source bibliographique ; les seuils évitent la fatigue d'alerte ; acquittement tracé.
8. **Bandeau « aide à la décision, aucun diagnostic »** sur chaque écran et chaque export comportant une sortie IA.

---

## 5. Référentiel clinique : règles corrigées

Règles et seuils **validés par l'encadrant (2026-11-11)** ; chaque règle cite la recommandation publiée dont elle découle.

| ID | Règle | Condition | Source |
|---|---|---|---|
| OBS_FEV1_FVC | Trouble ventilatoire obstructif | VEMS/CVF < 0,70 **post-bronchodilatateur** uniquement | GOLD 2025 |
| FEV1_DECLINE | Déclin du VEMS | Baisse ≥ 100 mL sur ≤ 12 mois (≥ 3 points, pente Theil-Sen) | ERS/ATS 2022 (interprétation des EFR) |
| PPF_FVC | Critère physiologique de progression (1 sur 3) | Baisse absolue de la CVF ≥ 5 % du prédit sur 1 an | ATS/ERS/JRS/ALAT 2022 |
| PPF_DLCO | Critère physiologique de progression (1 sur 3) | Baisse absolue de la DLCO ≥ 10 % du prédit sur 1 an | ATS/ERS/JRS/ALAT 2022 |
| CRP_RISE | Syndrome inflammatoire | CRP > 10 mg/L **et** en hausse vs la valeur précédente | Seuil biologique usuel |
| CRP_NOT_NORMALIZED | Non-normalisation | CRP > 5 mg/L ≥ 14 jours après le début d'un antibiotique | Parcours B |
| SPO2_LOW | Hypoxémie | SpO2 < 92 % **au repos, air ambiant** | BTS 2017 (oxygénothérapie) |
| EOS_HIGH | Éosinophilie (aide au choix des corticoïdes inhalés) | Éosinophiles ≥ 0,3 G/L | GOLD 2025 |

Les alertes PPF sont libellées « critère physiologique de progression », **jamais** « fibrose progressive » (le diagnostic exige 2 critères sur 3, dont les symptômes et l'imagerie).

---

## 6. Données

### 6.1 Radiographies

| Besoin | Dataset | Licence | Usage |
|---|---|---|---|
| Séries adultes pour la démo et le suivi | **NIH ChestX-ray14** : sous-ensemble de 40 à 60 patients ≥ 18 ans, ≥ 3 radios de face, étiquettes d'intérêt | usage non restreint, attribution obligatoire (Wang et al., CVPR 2017 ; NIH Clinical Center) | Démo, séries temporelles, dates synthétiques ordonnées par `Follow-up #` |
| Évaluation de l'imagerie (étiquettes relues par des radiologues) | **RSNA Pneumonia Detection Challenge**, 1 000 à 2 000 images adultes | Règles de la compétition Kaggle (à accepter sur Kaggle avant le téléchargement) | AUC pneumonie / opacité |
| Modèle | **TorchXRayVision** `densenet121-res224-all` (application) et `-chex` (évaluation externe) | Code Apache-2.0 ; poids issus de jeux à usage recherche (suffisant pour le PFA) | Inférence CPU |

- Kermany (pédiatrique) a été supprimé. 136 Go libres : NIH complet (≈ 42 Go) est possible, mais le sous-ensemble suffit.
- **Limite connue** : les poids `-all` ont vu NIH et RSNA à l'entraînement, donc leur AUC sur ces jeux est optimiste. On rapporte deux mesures : `-all` (interne, optimiste) et `-chex` sur RSNA (externe, plus honnête).
- **Métadonnées utilisées** : âge et sexe (analyse de biais), `View Position` (filtre PA/AP), `Patient ID` (séparation au niveau patient).

### 6.2 Dossiers synthétiques (générateur maison)

- 36 patients (12 par parcours), 4 à 8 visites, 12 mois ; trajectoires par parcours (exacerbations, résolution, déclin) avec bruit de mesure réaliste.
- Documents : bilans biologiques, EFR (valeurs absolues + % du prédit fournis directement), comptes rendus, ordonnances.
- **4 gabarits de laboratoire** : 3 pour le développement, **1 tenu à l'écart** (jamais vu pendant la mise au point) pour limiter l'évaluation circulaire.
- 30 % des PDF dégradés en scans (bruit, rotation, flou, JPEG).
- Vérité terrain écrite par construction ; `splits.json` figé : 30 patients dev / 6 test.
- Chaque patient synthétique est apparié à un patient NIH du même profil (étiquettes, sexe, âge proche). Limite documentée : cohérence clinique simulée.

### 6.3 Évaluation

- `evaluation/questions_60.jsonl` : 60 questions cliniques, réponses calculées depuis la vérité terrain.

---

## 7. Architecture

### 7.1 Vue d'ensemble

```
[React + TS (Vite, Tailwind, Recharts)]
            │ HTTPS (proxy Caddy)
[FastAPI] ── auth, patients, documents, measurements, series, imaging, alerts, summaries, chat, audit, jobs
   │  services : ingestion · normalize · trends · alerts · imaging · summary · verifier · rag
   ├── PostgreSQL 16 (données structurées, JSONB)
   ├── Volume `storage` (fichiers, Grad-CAM, PDF)
   ├── ChromaDB embarqué (T3, RAG)
   └── Ollama (sur l'hôte Windows, via host.docker.internal:11434)
```

- **Docker Compose** : `db`, `backend` (image avec Tesseract `fra`, PyTorch CPU, TorchXRayVision), `frontend`, `proxy` (Caddy, TLS local).
- **Ollama sur l'hôte** : il est déjà installé, et il est plus simple et plus rapide sans GPU qu'en conteneur.
- **Asynchrone** : BackgroundTasks + table `jobs` ; pas de Celery ni de Redis.

### 7.2 Flux

Dépôt → job → texte/OCR (+ boîtes) → classification → extraction → normalisation → **validation par le médecin** → mesures → tendances et alertes / frise / imagerie → tableau de bord → fiche.

### 7.3 Modèle de données (écarts vs CdC en gras)

| Entité | Attributs |
|---|---|
| users | id, name, email, password_hash, role |
| patients | id, doctor_id, **birth_date**, sex, **height_cm**, antecedents, pack_years, allergies, base_treatments |
| documents | id, patient_id, type, exam_date, file_path, **sha256**, extracted_text, **ocr_boxes (JSONB)**, status, confidence |
| parameters | code, name, synonyms[], unit, alt_units, plausible_min/max, ref_low/high |
| measurements | id, patient_id, parameter_code, value, unit, date, **context**, source_document_id, **bbox**, confidence, validation_status, **validated_by, validated_at** |
| treatments | id, patient_id, molecule, dosage, start_date, end_date, source_document_id, validation_status |
| clinical_events | id, patient_id, type, date, note, source_document_id |
| imaging | id, document_id, date, **view**, **quality_flag**, scores (JSONB), **uncertainty (JSONB)**, gradcam_path, **model_name, model_version**, doctor_assessment |
| alerts | id, patient_id, rule_id, **ruleset_version**, source_values (JSONB), date, state, **acknowledged_by, acknowledged_at** |
| consultation_sheets | id, patient_id, date, facts (JSONB), text, **mode (template/llm)**, verification (JSONB), pdf_path |
| conversations (T3) | id, user_id, patient_id, messages, cited_sources |
| audit_log | id, user_id, action, object_type, object_id, timestamp |
| jobs | id, type, ref_id, status, error, created_at, finished_at |

Index `(patient_id, parameter_code, date)` ; toute requête filtre par `doctor_id`.

### 7.4 Structure du dépôt

```
medimind-ai/
├── CLAUDE.md · README.md · docker-compose.yml · .env.example · Caddyfile
├── docs/        PLAN.md, DECISIONS.md, PROGRESS.md, architecture.md, model-card.md, evaluation-report.md, uml/, mockups/
├── referential/ referentiel_clinique.yaml
├── synthetic/   generator/, templates/ (4), out/ (gitignored), ground_truth/, splits.json
├── backend/     app/{core,db,api,services,schemas}, tests/
├── frontend/    src/{pages,components,charts,viewer,api,hooks}
├── ml/          scripts/{select_nih_patients.py, eval_imaging.py}, weights/ (gitignored)
├── evaluation/  questions_60.jsonl, run_*_eval.py, protocols/
└── data/        (gitignored) nih_subset/, rsna_subset/
```

---

## 8. Exigences non fonctionnelles

| Catégorie | Exigence |
|---|---|
| Performance (CPU i5, 16 Go) | Courbes 1 an < 2 s ; PDF natif < 30 s ; scan < 60 s ; radio < 5 s ; fiche gabarit < 5 s ; fiche reformulée par LLM < 60 s (D10) |
| Sécurité | TLS (Caddy), bcrypt, JWT à expiration courte, rôles, isolation par médecin/patient, secrets dans `.env` |
| Confidentialité | Données publiques/synthétiques ; LLM local ; journal d'accès ; effacement d'un patient (cascade + fichiers) |
| Fiabilité | Jobs consultables et rejouables ; erreurs explicites |
| Explicabilité | Source et zone de chaque valeur ; règle et référence de chaque alerte ; scores + incertitude + Grad-CAM |
| Ergonomie | Français, écran unique de suivi, responsive |
| Maintenabilité | Tests (pytest, Playwright e2e), CI GitHub Actions (ruff, eslint, pytest, build) |

---

## 9. Évaluation

| Composant | Protocole | Cible |
|---|---|---|
| Extraction | P/R/F1 par champ sur 6 patients de test, **gabarits de dev vs gabarit tenu à l'écart** | F1 ≥ 0,95 natif, ≥ 0,85 scans (gabarits de dev) ; écart avec le gabarit tenu à l'écart rapporté |
| Normalisation | Exactitude paramètre + unité + contexte | ≥ 95 % |
| Tendances / alertes | Cas de référence unitaires + parcours A/B/C | 100 % |
| Imagerie | AUC par pathologie ; `-chex` sur RSNA (externe) + `-all` (interne, optimiste) ; analyse par âge et sexe | AUC pneumonie ≥ 0,75 en externe |
| Fiche | % des nombres vérifiés ; ablation LLM seul vs faits + vérificateur | 100 % après vérificateur |
| RAG (T3) | Fidélité et citations sur 60 questions | ≥ 85 % |
| Utilité | Test chronométré 5 questions avec/sans outil + SUS, avec l'encadrant et des étudiants : **évaluation proxy, non clinique** | Temps −50 %, SUS ≥ 70 |

Ablation supplémentaire : extraction règles seules / LLM seul / hybride.

---

## 10. Roadmap (par tranches)

> Planification détaillée, étape par étape, jusqu'à la soutenance : **`docs/ROADMAP.md`**.

| Jalon | Contenu | Critère de sortie |
|---|---|---|
| **J0 Cadrage** | PLAN validé par l'encadrant, référentiel v0, 4 maquettes (évolution, comparateur, validation, fiche), `DECISIONS.md` | Encadrant d'accord |
| **J1 Socle (T1)** | Dépôt, Compose, auth, modèles + migrations, jobs, audit, générateur synthétique, sous-ensemble NIH | `docker compose up` → connexion ; 36 patients générés |
| **J2 Chaîne bout en bout (T1)** | A2 → A8, B1/B2, C1/C2 | Parcours A : dépôt → validation → courbe + score radio |
| **J3 Analyse (T2)** | B3–B5, C3–C5, D1/D2/D4, E1–E3 | Démo complète des 3 parcours, fiche vérifiée |
| **J4 Compléments (T3)** | B6–B8, C6–C8, E4 | Selon le temps restant ; coupe dans l'ordre E4 → C8 → B8 → autres |
| **J5 Qualité et évaluation** | Tests de sécurité/accès croisé, e2e, campagne §9, model card | Rapport d'évaluation |
| **J6 Livrables** | README, rapport, vidéo, soutenance, test de reproductibilité (clone propre) | Livrables du CdC §18 |

Démonstration à l'encadrant à la fin de J2, J3 et J5.

---

## 11. Risques techniques

| Risque | Impact | Mesure |
|---|---|---|
| Lenteur du LLM sur CPU | Moyen | Gabarit déterministe par défaut ; modèle 3B ; LLM optionnel |
| OCR de scans médiocre | Moyen | Natifs prioritaires, prétraitement, validation humaine obligatoire |
| Évaluation d'extraction circulaire | Moyen | Gabarit tenu à l'écart ; limite documentée |
| AUC optimiste (fuite des poids) | Élevé | Double mesure interne/externe ; limite dans la model card |
| Étiquettes NIH bruitées | Moyen | RSNA (relu par des radiologues) pour l'évaluation |
| Pas de clinicien | Moyen | Règles sourcées, validation par l'encadrant, évaluation proxy explicite |
| Périmètre | Moyen | Tranches + ordre de coupe (§10) |

---

## 12. Réglementaire et données personnelles

### 12.1 Pendant le PFA (démonstrateur)

- Aucune donnée réelle : pas de traitement de données personnelles au sens de la loi 09-08.
- Mention « Démonstrateur de recherche, non dispositif médical, ne pas utiliser pour une décision clinique » dans l'application, le README et la model card.
- Respect des licences : attribution NIH ; vérification des conditions RSNA avant téléchargement ; mention des licences des poids.

### 12.2 Perspective hors PFA : si un jour commercialisation au Maroc (à confirmer avec un juriste le moment venu)

> Non requis pour la soutenance. Sert au chapitre « Perspectives » du rapport et aux questions du jury.

| Sujet | Exigence |
|---|---|
| Statut du logiciel | Un logiciel produisant des scores de pathologie relève probablement des **dispositifs médicaux** (loi 84-12 ; autorité : Direction du Médicament et de la Pharmacie). Prévoir un dossier technique, la gestion des risques (ISO 14971), le cycle de vie logiciel (IEC 62304), l'aptitude à l'utilisation (IEC 62366) et la cybersécurité. |
| Données de santé | **Loi 09-08** : données sensibles ⇒ **autorisation préalable de la CNDP** ; consentement ; droits d'accès, de rectification et d'opposition ; sécurité ; **transfert hors du Maroc soumis à autorisation** (d'où LLM et hébergement locaux). |
| Hébergement | Hébergement au Maroc, chiffrement au repos, sauvegardes, journalisation. |
| Données d'entraînement | Remplacer les poids et datasets non commerciaux (CheXpert, MIMIC, RSNA) par des données sous licence commerciale ou des données marocaines (convention hospitalière + CNDP + comité d'éthique). |
| Validation clinique | Étude sur données réelles locales, avec des pneumologues. |
| UE (si un jour) | RGPD art. 9 ; MDR (règle 11 ⇒ classe IIa minimum) ; AI Act (IA d'un dispositif médical = haut risque). |

---

## 13. Décisions et écarts vs cahier des charges

| # | Décision | Raison |
|---|---|---|
| D1 | Patients adultes uniquement | Utilisateur pneumologue adulte ; modèles et normes adultes |
| D2 | Kermany retiré ; NIH (sous-ensemble) + RSNA | Kermany pédiatrique, sans série, val inutilisable |
| D3 | Ollama local uniquement, Groq retiré | Loi 09-08 (transfert), pas de dépendance externe |
| D4 | Fiche par gabarit déterministe par défaut, LLM optionnel | CPU sans GPU ; zéro hallucination de structure |
| D5 | F-C6 = « variation des scores », pas de verdict IA ; cible de 70 % supprimée | Non mesurable sans vérité terrain d'évolution |
| D6 | F-D3 et F-E5 retirées | Hors fil conducteur / risque clinique |
| D7 | Règles d'alerte corrigées et sourcées (§5) | Erreurs cliniques du CdC (contexte post-BD, fatigue d'alerte) |
| D8 | F-A9 audit et F-A8 validation en T1 | Socle de la confiance et de la traçabilité |
| D9 | Gabarit de labo tenu à l'écart | Limiter l'évaluation circulaire |
| D10 | Budget de la fiche LLM : 60 s | Matériel CPU |
| D11 | Pas d'affinage (fine-tuning) | Pas de GPU ; pré-entraîné suffisant pour un démonstrateur |

## 14. Validation

Plan, écarts D1–D11, fonctionnalités, règles et seuils validés par l'encadrant le 2026-11-11. Aucune question ouverte.
