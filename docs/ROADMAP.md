# MediMind AI : planification détaillée jusqu'à la soutenance

> Complète `docs/PLAN.md` (le *quoi*) par le *comment et dans quel ordre*. Les identifiants F-xx renvoient au §3 du plan.
> **Règle de progression** : on ne passe à l'étape suivante que lorsque son « Terminé quand » est vrai. Chaque étape terminée est cochée dans `docs/PROGRESS.md` et fait l'objet d'un commit ou d'un tag.
> **Responsables** : **I** = Ishak (backend, ingestion, B/D/E, sécurité, Docker) · **S** = Ismail (imagerie, frontend, UX) · **I+S** = partagé.
> **Pistes parallèles** : à partir de la phase 2, Ishak avance sur le backend (A → B/D → E) pendant qu'Ismail avance sur le frontend et l'imagerie (C). Les points de synchronisation sont marqués ⟷.

---

## Vue d'ensemble

| Phase | Contenu | Livrable | Démo encadrant |
|---|---|---|---|
| 0 | Cadrage et environnement | Plan validé, référentiel v0, maquettes | ✔ |
| 1 | Données | NIH, RSNA, 36 dossiers synthétiques, patient démo | |
| 2 | Socle applicatif | `docker compose up` → login | |
| 3 | Module A : ingestion | Dépôt → extraction → validation | ✔ |
| 4 | Modules B + D : courbes, frise, alertes | Écran d'évolution complet | |
| 5 | Module C : imagerie | Scores, Grad-CAM, comparateur | ✔ |
| 6 | Module E + intégration | Fiche vérifiée, écran unique | ✔ (démo complète) |
| 7 | Compléments T3 | P2/P3 retenues | |
| 8 | Qualité et sécurité | Tests verts, TLS, seed, reproductibilité | |
| 9 | Évaluation | Rapport d'évaluation, model card | ✔ |
| 10 | Livrables et soutenance | Rapport, vidéo, slides, répétition | ✔ (blanc) |

---

## Phase 0 : Cadrage et environnement

### 0.1 Validation avec l'encadrant (I+S)
- [ ] Présenter `docs/PLAN.md`, en particulier les écarts au CdC (§13, D1–D11).
- [ ] Noter ses réponses dans `docs/DECISIONS.md` (une entrée par écart : accepté / refusé / modifié).
- [ ] Lui demander s'il connaît un pneumologue joignable (même 15 minutes) pour relire les seuils du §5.
- **Terminé quand** : chaque écart a une décision écrite.

### 0.2 Environnement de travail (I+S)
- [ ] `git init`, dépôt GitHub **privé**, `.gitignore` (data/, weights/, synthetic/out/, .env, node_modules, __pycache__).
- [ ] Outils : Docker Desktop, Python 3.11, Node 20 LTS, Git ; vérifier `ollama run llama3.2:3b "bonjour"`.
- [ ] Compte Kaggle + jeton API (`kaggle.json`, jamais committé).
- [ ] Protection de la branche `main` (pull requests + revue croisée).
- **Terminé quand** : les deux machines clonent le dépôt et Ollama répond.

### 0.3 Référentiel clinique v0 (I)
- [ ] `referential/referentiel_clinique.yaml` : environ 20 paramètres (VEMS, CVF, VEMS/CVF, CVF % prédit, VEMS % prédit, DLCO % prédit, SpO2, CRP, PCT, leucocytes, PNN, lymphocytes, éosinophiles, Hb, plaquettes, créatinine, pH, PaO2, PaCO2, HCO3), avec synonymes, unités, conversions, bornes plausibles et bornes de référence.
- [ ] Règles d'alerte du §5 du plan, chacune avec `id`, `condition`, `source`, `label`.
- [ ] Champ `version: 0.1`.
- **Terminé quand** : le fichier est relu par l'encadrant et un test de schéma est prévu à l'étape 2.2.

### 0.4 Conception (I+S)
- [ ] 15 user stories du pneumologue (`docs/user-stories.md`), format « En tant que… je veux… afin de… », chacune reliée à un F-xx.
- [ ] UML (`docs/uml/`, PlantUML ou draw.io) : cas d'usage ; séquences « dépôt → validation » et « génération de fiche » ; diagramme de classes (= modèle de données §7.3).
- [ ] Diagramme d'architecture et de flux (`docs/architecture.md`).
- **Terminé quand** : les diagrammes sont dans le dépôt et cohérents avec le plan.

### 0.5 Maquettes (S)
- [ ] 4 écrans : (1) **évolution** (courbes + frise + alertes), (2) **comparateur de radios**, (3) **validation** (document ↔ valeurs), (4) **fiche pré-consultation**. Plus la connexion et la liste des patients.
- [ ] Outil : Figma ou prototype HTML. Charte : sobre, médicale, lisible ; bandeau « aide à la décision » visible.
- **Terminé quand** : l'encadrant a vu les maquettes ; ses retours sont notés.

### 0.6 Suivi (I+S)
- [ ] `docs/PROGRESS.md` (cases de ce fichier) ; `docs/DECISIONS.md` ; tableau GitHub Projects avec une issue par F-xx.

**✔ Démo encadrant 1** : plan, maquettes, référentiel.

---

## Phase 1 : Données

### 1.1 Sous-ensemble NIH ChestX-ray14 (S)
- [ ] Télécharger `Data_Entry_2017.csv` (+ `BBox_List_2017.csv`).
- [ ] Script `ml/scripts/select_nih_patients.py`, critères : âge ≥ 18 et ≤ 90 (exclure les âges aberrants), `View Position` = PA ou AP, ≥ 3 radios par patient, étiquettes d'intérêt (Pneumonia, Consolidation, Infiltration, Effusion, Atelectasis, Emphysema, Fibrosis, Cardiomegaly, No Finding).
- [ ] Choisir environ 60 patients : 20 profils BPCO/emphysème, 20 profils pneumonie/consolidation, 20 profils fibrose, équilibrés en sexe.
- [ ] Télécharger seulement ces images (Kaggle, fichier par fichier) dans `data/nih_subset/`.
- [ ] `data/nih_subset/manifest.csv` : patient NIH, image, rang de suivi, étiquettes, âge, sexe, **date synthétique** (ordonnée selon `Follow-up #`, espacée de 1 à 4 mois).
- [ ] `data/ATTRIBUTION.md` : citation Wang et al. 2017 et NIH Clinical Center.
- **Terminé quand** : le manifest est complet et les images s'ouvrent.

### 1.2 Sous-ensemble RSNA (S)
- [ ] Lire et accepter les règles de la compétition Kaggle ; noter la licence dans `data/ATTRIBUTION.md`.
- [ ] Sélectionner environ 1 500 images adultes (âge lu dans le DICOM), environ 1/3 positives, **un patient = une image**.
- [ ] Convertir DICOM → PNG (pydicom) dans `data/rsna_subset/` + `labels.csv`.
- **Terminé quand** : `labels.csv` est équilibré et documenté.

### 1.3 Générateur de dossiers synthétiques (I, S en support)
- [ ] `synthetic/generator/trajectories.py` : simulation par parcours.
  - **A, BPCO** : VEMS en déclin d'environ 40 à 80 mL/an, avec bruit ; 1 à 3 exacerbations (pic de CRP et de leucocytes, chute de SpO2) ; changement de traitement (ajout d'un corticoïde inhalé) suivi d'une stabilisation.
  - **B, pneumonie** : CRP, leucocytes et PCT élevés à J0, puis décroissance après antibiotique ; normalisation entre J14 et J30 ; 1 patient sur 4 sans normalisation (pour tester l'alerte).
  - **C, fibrose** : CVF % prédit −3 à −8 %/an ; DLCO % prédit −5 à −12 %/an ; SpO2 en baisse lente.
- [ ] `events.py` : exacerbations, hospitalisations, ordonnances (DCI réalistes : tiotropium, salmétérol/fluticasone, amoxicilline-acide clavulanique, prednisolone, nintédanib…).
- [ ] `templates/` : **4 gabarits** HTML de laboratoire (mise en page, noms de paramètres, unités et ordre des colonnes différents) + gabarits EFR, compte rendu et ordonnance. Rendu PDF avec WeasyPrint.
- [ ] `degrade.py` : 30 % des PDF convertis en image (rotation ±3°, bruit, flou, JPEG qualité 60-80).
- [ ] `pairing.py` : chaque patient synthétique reçoit une série NIH cohérente (parcours ↔ étiquettes ; même sexe, âge proche). Les dates des radios sont alignées sur les visites.
- [ ] Sorties : `synthetic/out/{patient_id}/` (documents + radios) et `synthetic/ground_truth/{patient_id}.json` (chaque valeur : paramètre, valeur, unité, date, contexte, document, gabarit).
- [ ] `synthetic/splits.json` figé : 30 dev / 6 test (2 par parcours). Le 4ᵉ gabarit n'est utilisé que dans les documents de test.
- [ ] Seed aléatoire fixe ; un seul point d'entrée `python -m synthetic.generator --seed 42`.
- **Terminé quand** : 36 dossiers générés ; un PDF de chaque gabarit est contrôlé visuellement ; la vérité terrain est cohérente avec les PDF (test automatique de comparaison du texte).

### 1.4 Jeu de questions et patient de démo (I+S)
- [ ] `evaluation/questions_60.jsonl` : 60 questions (20 par parcours), réponses calculées automatiquement depuis la vérité terrain.
- [ ] Patient de démo **« M. A., BPCO, 12 mois »** : 6 visites, 2 exacerbations, 1 changement de traitement, 4 radios ; documents mêlant PDF natifs et scans.
- **Terminé quand** : le scénario de démo est écrit dans `docs/demo-scenario.md`.

---

## Phase 2 : Socle applicatif

### 2.1 Infrastructure (I)
- [ ] Structure du dépôt (§7.4 du plan).
- [ ] `docker-compose.yml` : `db` (postgres:16), `backend`, `frontend`, `proxy` (Caddy) ; volume `storage` ; `extra_hosts: host.docker.internal` pour Ollama.
- [ ] `.env.example` (DB, JWT_SECRET, OLLAMA_URL, OLLAMA_MODEL, STORAGE_PATH).
- [ ] Image backend : python:3.11-slim + `tesseract-ocr tesseract-ocr-fra` + torch CPU + torchxrayvision + PyMuPDF + WeasyPrint.
- **Terminé quand** : `docker compose up` démarre les 4 services sans erreur.

### 2.2 Squelette backend (I)
- [ ] FastAPI : `core/config.py` (pydantic-settings), journalisation JSON, gestion d'erreurs uniforme.
- [ ] SQLAlchemy 2 : tous les modèles du §7.3 ; migration Alembic initiale ; index.
- [ ] Chargement du référentiel au démarrage + **test de schéma YAML**.
- [ ] `GET /health` (DB, Ollama, modèle d'imagerie).
- **Terminé quand** : `pytest` est vert et `/health` renvoie l'état de chaque dépendance.

### 2.3 Authentification et isolation, F-A1 (I)
- [ ] `POST /auth/login`, `/auth/refresh` ; création des utilisateurs par l'admin (pas d'inscription publique).
- [ ] bcrypt ; JWT d'accès 15 min, refresh 7 jours.
- [ ] Dépendances `current_user`, `require_role`, `get_patient_for_doctor` (404 si le patient n'appartient pas au médecin).
- [ ] Tests : accès croisé entre deux médecins ; l'admin n'accède à aucun endpoint patient.
- **Terminé quand** : tous les tests d'accès sont verts.

### 2.4 Jobs et audit, F-03 et F-A9 (I)
- [ ] Service `jobs` (création, statut, erreur, relance) ; `GET /jobs/{id}`, `POST /jobs/{id}/retry`.
- [ ] Middleware ou service d'audit : lecture d'un patient, correction, validation, génération IA.
- **Terminé quand** : un job en échec forcé est relancé avec succès ; l'audit contient les actions.

### 2.5 Squelette frontend (S)
- [ ] Vite + React + TS + Tailwind ; React Router ; React Query ; client API avec rafraîchissement du token.
- [ ] Pages : connexion, liste des patients, mise en page avec **composant `DecisionSupportBanner`**.
- [ ] Design system minimal (couleurs, typographie, composants carte / tableau / badge de statut).
- **Terminé quand** : connexion → liste des patients (vide) via le proxy en HTTPS.

### 2.6 Intégration continue (I)
- [ ] GitHub Actions : ruff + pytest (backend) ; eslint + tsc + build (frontend).
- **Terminé quand** : la CI est verte sur `main`.

⟷ **Synchronisation** : contrat d'API (OpenAPI généré par FastAPI) partagé ; types TS générés (`openapi-typescript`).

---

## Phase 3 : Module A, ingestion

### 3.1 Fiche patient, F-A2 (I backend, S frontend)
- [ ] CRUD `/patients` ; validation : âge ≥ 18, sexe, taille, paquets-années ≥ 0.
- [ ] Formulaire + page de détail du patient.
- **Terminé quand** : la création d'un patient mineur est refusée avec un message clair.

### 3.2 Téléversement, F-A3 (I, S)
- [ ] `POST /patients/{id}/documents` (multi-fichiers, date d'examen, type facultatif) ; SHA-256 ; stockage `storage/{patient}/{doc}` ; création d'un job.
- [ ] Interface glisser-déposer + suivi d'état des jobs (sondage de React Query).
- **Terminé quand** : un doublon est signalé et un dépôt de 5 fichiers crée 5 jobs.

### 3.3 Extraction du texte, F-A4 (I)
- [ ] PDF natif : PyMuPDF, mots + boîtes englobantes par page.
- [ ] Détection natif / scan (peu de texte ⇒ scan).
- [ ] Scan : rendu de la page en 300 dpi, redressement, binarisation (OpenCV), Tesseract `fra` via `image_to_data` ⇒ mots, boîtes, confiance.
- [ ] Stockage : `extracted_text`, `ocr_boxes` (JSONB), confiance moyenne.
- **Terminé quand** : sur 10 documents de dev, le texte est lisible et les boîtes sont superposables à l'image.

### 3.4 Classification, F-A5 (I)
- [ ] Règles par mots-clés pondérés (ex. « VEMS », « CVF », « DLCO » ⇒ EFR ; « posologie », « comprimé » ⇒ ordonnance).
- [ ] Repli LLM (Ollama, `format` = schéma JSON) si le score des règles est sous un seuil.
- **Terminé quand** : ≥ 95 % de documents bien classés sur le jeu de dev.

### 3.5 Extraction structurée, F-A6 (I)
- [ ] Parseur générique de tableaux de laboratoire : regroupement des mots en lignes via les boîtes ; motif `libellé · valeur · unité · [bornes]`.
- [ ] Regex dédiées : date d'examen, contexte (« post-BD », « après bronchodilatateur », « sous O₂ »).
- [ ] Repli LLM pour le texte libre (comptes rendus) : prompt « extraire uniquement ce qui est écrit », schéma JSON imposé, puis **vérification que chaque valeur figure littéralement dans le texte source** (sinon rejet).
- [ ] Sortie Pydantic `ExtractedValue` avec `bbox` et `source_text`.
- **Terminé quand** : aucune valeur sans `source_text` ; tests sur les 3 gabarits de dev.

### 3.6 Normalisation, F-A7 (I)
- [ ] Correspondance de libellés (synonymes + correspondance approchée avec seuil, rapidfuzz).
- [ ] Conversions (mL→L, g/dL→g/L, %↔ratio pour VEMS/CVF, /mm³→G/L).
- [ ] Contrôle de plausibilité (hors bornes ⇒ statut `suspect`) ; dédoublonnage (même paramètre, même date, même valeur).
- **Terminé quand** : tests unitaires par paramètre et par conversion verts.

### 3.7 Écran de validation, F-A8 (S frontend, I API)
- [ ] API : `GET /documents/{id}/extractions`, `PATCH /measurements/{id}` (valider / corriger / rejeter) ; validation groupée.
- [ ] UI : document à gauche (pdf.js ou image) avec **surlignage de la boîte** au survol ; tableau des valeurs à droite ; badges de confiance ; raccourcis clavier (Entrée = valider, E = éditer).
- [ ] Les traitements (F-D1) et événements (F-D4) passent par le même écran (onglets).
- **Terminé quand** : un document de démo est validé entièrement en moins d'une minute.

### 3.8 Évaluation de l'extraction en dev (I)
- [ ] `evaluation/run_extraction_eval.py` : P/R/F1 par champ, par gabarit, natif vs scan, sur les 30 patients de dev.
- **Terminé quand** : le premier rapport est produit ; les erreurs principales sont corrigées (F1 natif ≥ 0,95 en dev).

**✔ Démo encadrant 2** : dépôt → extraction → validation sur le patient de démo.

---

## Phase 4 : Modules B et D, évolution, traitements, alertes

### 4.1 API de séries (I)
- [ ] `GET /patients/{id}/series?params=&from=&to=` (mesures validées uniquement ; non validées dans un champ séparé).
- [ ] `GET /patients/{id}/timeline` (traitements + événements + radios).
- **Terminé quand** : réponse < 300 ms pour 1 an.

### 4.2 Courbes et période, F-B1 et F-B2 (S)
- [ ] Sélecteur 3 m / 6 m / 1 an / tout / personnalisé.
- [ ] Courbes Recharts multi-paramètres en petits multiples alignés sur un axe temporel commun ; zones de référence ; points hors normes marqués ; infobulle avec lien vers le document source.
- **Terminé quand** : affichage d'un an en moins de 2 s ; clic sur un point → document source.

### 4.3 Traitements et événements, F-D1 et F-D4 (I)
- [ ] Extraction des ordonnances : DCI (dictionnaire d'environ 50 molécules respiratoires + synonymes commerciaux), posologie, date de début ; durée si précisée.
- [ ] Événements : saisie manuelle + extraction depuis les comptes rendus (« exacerbation », « hospitalisation »).
- **Terminé quand** : les traitements du patient de démo sont extraits et validés.

### 4.4 Frise et annotations, F-D2 et F-B3 (S)
- [ ] Frise horizontale (barres = traitements, losanges = événements, icônes = radios) partageant l'axe des courbes.
- [ ] Lignes verticales d'événements sur toutes les courbes.
- **Terminé quand** : alignement au pixel près entre la frise et les courbes, quelle que soit la période.

### 4.5 Tendances, F-B4 (I)
- [ ] Theil-Sen (scipy) ; variation absolue et relative ; qualification par seuils propres à chaque paramètre ; « données insuffisantes » si moins de 3 points.
- [ ] Affichage : pente annualisée + étiquette de qualification + nombre de points.
- **Terminé quand** : tests sur cas de référence verts à 100 %.

### 4.6 Alertes, F-B5 (I backend, S UI)
- [ ] Moteur générique lisant les règles du YAML (seuil, variation sur fenêtre, condition de contexte) ; recalcul à chaque validation.
- [ ] Alerte = règle + libellé + **source bibliographique** + valeurs déclenchantes (liens) + version du référentiel.
- [ ] Panneau d'alertes, acquittement tracé.
- **Terminé quand** : sur les 36 patients, les alertes attendues (déduites de la vérité terrain) se déclenchent, et seulement elles.

---

## Phase 5 : Module C, imagerie

### 5.1 Service d'inférence, F-C1 et F-C2 (S)
- [ ] Chargement unique du modèle au démarrage (`densenet121-res224-all`), CPU.
- [ ] Prétraitement TorchXRayVision (niveaux de gris, normalisation, recadrage central, 224 px).
- [ ] Garde-fous : patient ≥ 18 ans ; vue frontale (métadonnée saisie ou NIH ; à défaut, confirmation par le médecin au téléversement) ; contrôle de qualité simple (taille minimale, contraste).
- [ ] Sauvegarde : scores des pathologies retenues, nom et version du modèle.
- **Terminé quand** : inférence < 5 s sur CPU ; les scores sont stockés.

### 5.2 Grad-CAM et incertitude, F-C3 (S)
- [ ] Grad-CAM sur la dernière couche convolutive (pytorch-grad-cam) pour la pathologie choisie ; PNG superposable.
- [ ] Augmentation à l'inférence (5 à 8 variantes : petites rotations, translations, contraste) ⇒ moyenne ± écart-type.
- [ ] Légende fixe : « zone d'attention du modèle, pas une localisation de lésion ».
- **Terminé quand** : le temps total radio + Grad-CAM + augmentation est mesuré et documenté.

### 5.3 Liste et visionneuse comparative, F-C1 et F-C4 (S)
- [ ] Liste chronologique en vignettes.
- [ ] Visionneuse à deux panneaux R(n) / R(n-1) ou au choix ; zoom et déplacement synchronisés ; curseur de superposition (opacité) ; activation de la carte Grad-CAM.
- **Terminé quand** : comparaison fluide sur le patient de démo.

### 5.4 Courbe des scores, F-C5 (S)
- [ ] Courbe des scores (± incertitude) dans le même composant d'axe que la biologie.
- **Terminé quand** : la radio apparaît au même instant dans la frise, la courbe des scores et les annotations.

### 5.5 Évaluation de l'imagerie en dev (S)
- [ ] `evaluation/run_imaging_eval.py` : AUC par pathologie ; `-chex` sur RSNA (externe) ; `-all` sur RSNA et le sous-ensemble NIH (interne, optimiste) ; courbes ROC ; analyse par sexe et tranche d'âge ; intervalles de confiance par bootstrap.
- **Terminé quand** : la première mesure est faite ; la cible indicative est recalibrée et notée dans `DECISIONS.md`.

**✔ Démo encadrant 3** : écran d'évolution + imagerie comparée.

---

## Phase 6 : Module E et intégration

### 6.1 Dossier de faits, F-E2 étape 1 (I)
- [ ] `facts.py` : identité clinique, motif, dernières valeurs et variations depuis la dernière visite, tendances, alertes actives, traitements en cours et changements, radios comparées (variation des scores), points à aborder (règles : alerte non acquittée ⇒ point).
- [ ] Chaque fait porte sa référence (mesure / document).
- **Terminé quand** : le JSON de faits du patient de démo est relu à la main et juste.

### 6.2 Fiche gabarit et PDF, F-E1 (I backend, S mise en page)
- [ ] Gabarit Jinja2 → HTML → PDF (WeasyPrint), 1 page A4, renvois vers les sources, bandeau d'avertissement, date et version.
- [ ] Aperçu HTML dans l'application + téléchargement du PDF.
- **Terminé quand** : la fiche tient sur une page pour tous les patients de test.

### 6.3 Reformulation LLM et vérificateur, F-E2 étapes 2-3 (I)
- [ ] Option « rédaction assistée » : Ollama reformule la synthèse **à partir du JSON de faits seulement**.
- [ ] Vérificateur : extraction des nombres et dates (regex FR : virgule décimale, %, unités, dates jj/mm/aaaa et en lettres) ; chaque élément doit correspondre à un fait (tolérance d'arrondi définie) ; mots interdits (« diagnostic », « certain », noms de maladies non présents dans les faits).
- [ ] 2 échecs ⇒ repli sur le gabarit + mention « rédaction assistée indisponible ».
- **Terminé quand** : 100 % des fiches livrées passent le vérificateur ; le temps est mesuré.

### 6.4 Garde-fous, F-E3 (I+S)
- [ ] Bandeau sur chaque sortie IA ; refus de toute question hors dossier ; journalisation des générations.
- **Terminé quand** : la revue des écrans montre le bandeau partout où il faut.

### 6.5 Tableau de bord unique (S)
- [ ] Écran patient : en-tête (profil + alertes), courbes + frise, panneau radios, accès à la fiche ; responsive.
- **Terminé quand** : le scénario de démo complet se déroule sans changer de page plus de 2 fois.

**✔ Démo encadrant 4** : parcours A de bout en bout (dépôt → validation → courbes 6 mois/1 an → radios comparées → fiche).

---

## Phase 7 : Compléments T3

À faire dans cet ordre ; **ordre de coupe inverse** si le temps manque (E4 coupé en premier).

- [ ] 7.1 F-B6 tableau dernière / précédente / variation (S).
- [ ] 7.2 F-B7 export PNG/PDF du graphique (S).
- [ ] 7.3 F-C6 variation des scores entre deux radios + incertitude ; qualification saisie par le médecin (S).
- [ ] 7.4 F-C7 annotation du médecin sur la radio (flèche, texte, stockée en JSON) (S).
- [ ] 7.5 F-B8 comparaison de deux périodes (S).
- [ ] 7.6 F-E4 assistant RAG (I) : découpage des documents validés, multilingual-e5-small, ChromaDB ; **questions de valeurs ⇒ requête SQL** ; réponse avec citations (document, date) ; refus hors dossier.
- [ ] 7.7 F-C8 recalage (alignement ECC d'OpenCV) + carte de différence (S), optionnel.
- **Terminé quand** : chaque fonctionnalité retenue est testée et démontrable ; celles coupées sont notées dans `DECISIONS.md`.

---

## Phase 8 : Qualité et sécurité

### 8.1 Sécurité (I)
- [ ] TLS via Caddy ; en-têtes de sécurité ; CORS strict ; limitation du nombre de tentatives de connexion.
- [ ] Contrôle des fichiers téléversés (type MIME réel, taille maximale) ; noms de fichiers générés côté serveur.
- [ ] Suppression d'un patient (cascade base + fichiers + index RAG), tracée.
- [ ] Rechercher les secrets dans l'historique Git (gitleaks).
- **Terminé quand** : checklist sécurité (`docs/security-checklist.md`) entièrement cochée.

### 8.2 Tests (I+S)
- [ ] Unitaires : normalisation, conversions, tendances, alertes, vérificateur (≥ 80 % de couverture sur `services/`).
- [ ] Intégration : pipeline document → mesure en base.
- [ ] E2E Playwright : scénario de démo du parcours A.
- [ ] Performance : script mesurant les budgets du §8 du plan.
- **Terminé quand** : la CI est verte, tests e2e compris.

### 8.3 Reproductibilité (I)
- [ ] `scripts/seed_demo.py` : médecin de démo + 3 patients (un par parcours) déjà validés + patient de démo à valider en direct.
- [ ] Test sur une machine propre : `git clone` → `.env` → `docker compose up` → seed → démo, en suivant le README seulement.
- **Terminé quand** : la seconde machine (celle du binôme) réussit sans aide.

---

## Phase 9 : Évaluation finale (6 patients de test, jamais utilisés avant)

- [ ] 9.1 Extraction : P/R/F1 par champ, natif vs scan, **gabarits de dev vs gabarit tenu à l'écart** (I).
- [ ] 9.2 Normalisation et alertes : exactitude, concordance 100 % sur les cas de référence (I).
- [ ] 9.3 Imagerie : AUC finales avec intervalles de confiance, analyse par âge et sexe (S).
- [ ] 9.4 Fiche : taux de nombres vérifiés ; **ablation** LLM seul (sans faits) vs faits + vérificateur (I).
- [ ] 9.5 Ablation extraction : règles seules / LLM seul / hybride (I).
- [ ] 9.6 RAG, si livré : fidélité et citations sur les 60 questions (I).
- [ ] 9.7 Utilité, proxy : test chronométré (5 questions, avec/sans outil) + questionnaire SUS avec l'encadrant et 3 à 5 étudiants ; protocole écrit avant le test (I+S).
- [ ] 9.8 `docs/model-card.md` : modèle, données, usage prévu et interdit, performances, biais, limites (S).
- [ ] 9.9 `docs/evaluation-report.md` : tableau cibles vs résultats, causes des écarts (I+S).
- **Terminé quand** : chaque cible du §9 du plan a un résultat chiffré ou un écart expliqué.

**✔ Démo encadrant 5** : résultats d'évaluation.

---

## Phase 10 : Livrables et soutenance

### 10.1 Gel des fonctionnalités (I+S)
- [ ] Plus aucune fonctionnalité nouvelle : uniquement des corrections. Tag `v1.0-rc`.

### 10.2 Documentation technique (I+S)
- [ ] README : présentation, captures, installation, lancement, identifiants de démo, licences et attributions.
- [ ] Dossier de conception : architecture, UML, modèle de données, choix techniques (DECISIONS), sécurité.

### 10.3 Rapport final (I+S)
Plan proposé :
1. Introduction (contexte, problématique, objectifs)
2. État de l'art (extraction documentaire médicale, IA en radiographie thoracique, LLM et hallucinations, outils existants)
3. Analyse et conception (besoins, cas d'usage, architecture, données)
4. Réalisation (modules A à E, captures)
5. Évaluation (protocole, résultats, ablations, discussion)
6. Éthique, sécurité, réglementation (loi 09-08, statut non-DM, garde-fous)
7. Limites et perspectives (données réelles, validation clinique, certification, commercialisation)
8. Conclusion ; annexes (référentiel, prompts, model card)
- [ ] Relecture croisée + relecture par l'encadrant.

### 10.4 Vidéo de démonstration (S)
- [ ] Script de 3 à 5 minutes basé sur `docs/demo-scenario.md` ; enregistrement (OBS) ; sous-titres.

### 10.5 Présentation de soutenance (I+S)
- [ ] Environ 15 diapositives : problème → utilisateur → solution → architecture → démo (en direct + vidéo de secours) → résultats → garde-fous et éthique → limites → perspectives.
- [ ] Liste de questions probables du jury et réponses (fuite de données, hallucinations, statut réglementaire, pourquoi des données synthétiques, absence de clinicien, choix techniques).
- [ ] Deux soutenances à blanc, chronométrées.

### 10.6 Checklist finale (I+S)
- [ ] Livrables du CdC §18 : CdC, maquettes et conception, code + README, Docker Compose, générateur + données + référentiel, notebooks et rapport d'évaluation, rapport final + slides + vidéo.
- [ ] Démo testée sur la machine de soutenance ; vidéo de secours hors ligne ; Ollama et modèles préchargés.
- [ ] Tag `v1.0`.

**✔ Démo encadrant 6** : soutenance à blanc.
