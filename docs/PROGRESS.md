# Avancement

> Une ligne par étape de `docs/ROADMAP.md`. Statut : ⬜ à faire · 🟨 en cours · ✅ terminé · ✂️ coupé.

## Phase 0 : Cadrage et environnement

| Étape | Statut | Notes |
|---|---|---|
| 0.1 Validation avec l'encadrant | ✅ | Écarts D1–D11 acceptés le 2026-11-11 (`DECISIONS.md`) |
| 0.2 Environnement | ✅ | Dépôt GitHub privé Amaranix/MediMind relié et poussé ; Kaggle CLI configurée (jeton dans ~/.kaggle/access_token, hors dépôt). Reste côté binôme : cloner sur la machine d'Ishak |
| 0.3 Référentiel clinique v0 | ✅ | v0.1.0 : 20 paramètres, 8 règles sourcées, validé par l'encadrant |
| 0.4 Conception | ✅ | `user-stories.md` (18), `uml/` (cas d'usage, 2 séquences, classes), `architecture.md` |
| 0.5 Maquettes | ✅ | `docs/mockups/index.html` (connexion, patients, évolution, radiographies, validation, fiche) + `DESIGN.md`. À montrer à l'encadrant |
| 0.6 Suivi | 🟨 | `PROGRESS.md`, `DECISIONS.md`. Reste : GitHub Projects |

## Phase 1 : Données

| Étape | Statut | Notes |
|---|---|---|
| 1.1 Sous-ensemble NIH | ✅ | 60 patients (20/profil, 10 F / 10 H), 327 radios, 128 Mo ; `ml/scripts/select_nih_patients.py`, `download_nih_subset.py` |
| 1.2 Sous-ensemble RSNA | ✅ | 1 500 images adultes (500 positives, 665 F / 835 H), 543 Mo ; archive complète (T13), supprimée après extraction |
| 1.3 Générateur synthétique | ✅ | 36 patients, 846 documents (493 PDF natifs, 112 scans PDF, 74 photos, 167 radios), 4 gabarits (T4 test), vérité terrain contrôlée contre le texte des PDF |
| 1.4 Questions et démo | ✅ | `evaluation/questions_60.jsonl`, `docs/demo-scenario.md` (patient A01) |

## Phase 2 : Socle applicatif

| Étape | Statut | Notes |
|---|---|---|
| 2.1 Infrastructure | ✅ | `docker-compose.yml` (db, backend, frontend, proxy Caddy HTTPS :8443), `.env.example` |
| 2.2 Squelette backend | ✅ | FastAPI, 13 tables, migration Alembic 0001 (aller-retour vérifié), référentiel validé par schéma, `/api/health` |
| 2.3 Authentification et isolation | ✅ | JWT + cookie httpOnly, rôles, isolation médecin/patient, admin sans accès patient |
| 2.4 Jobs et audit | ✅ | Table `jobs`, relance, remise en échec au redémarrage ; audit des connexions et accès patients |
| 2.5 Squelette frontend | ✅ | Connexion, liste et création de patients (refus < 18 ans), page admin (comptes + état du service), bandeau permanent |
| 2.6 Intégration continue | ✅ | GitHub Actions : ruff + pytest, eslint + build, construction des images |

Tests : 29 tests backend verts ; parcours navigateur vérifié (connexion, session restaurée, refus mineur, redirections par rôle).

## Phase 3 : Module A, ingestion

| Étape | Statut | Notes |
|---|---|---|
| 3.1 Fiche patient | ✅ | Création (refus < 18 ans), fiche patient avec panneau d'identité et onglets |
| 3.2 Téléversement | ✅ | Multi-fichiers, glisser-déposer, type détecté par signature binaire, SHA-256 (doublons), tâche de fond |
| 3.3 Extraction du texte | ✅ | PDF natif (PyMuPDF) ; scans et photos : redressement, médian + Otsu, Tesseract `fra` ; boîtes normalisées |
| 3.4 Classification | ✅ | Règles pondérées, repli LLM local ; 100 % sur le jeu de développement |
| 3.5 Extraction structurée | ✅ | Bilans (4 mises en page), EFR (colonnes par en-tête ou par nombre de valeurs), comptes rendus (SpO2 + contexte, gaz du sang) |
| 3.6 Normalisation | ✅ | Synonymes, unités (correspondance approchée), plausibilité, contexte, dédoublonnage |
| 3.7 Écran de validation | ✅ | Document avec zones surlignées, valider / corriger / rejeter, clavier, validation groupée des seules valeurs sûres |
| 3.8 Évaluation (dev) | ✅ | 709 documents : F1 1,000 PDF natifs, 0,936 scans, 0,953 photos ; classification 100 % ; date 99,8 % ; 0,9 s/document |

Tests : 86 tests backend verts ; parcours navigateur vérifié dans Docker (dépôt de 4 documents dont un scan, doublon détecté, validation au clavier et groupée).

## Phase 4 : Modules B et D, évolution, traitements, alertes

| Étape | Statut | Notes |
|---|---|---|
| 4.1 API de séries | ✅ | Séries validées (pré-BD exclu), valeurs en attente séparées ; frise (traitements, changements, événements, radiographies) |
| 4.2 Courbes et période | ✅ | 3 mois / 6 mois / 1 an / tout, paramètres par pathologie suivie, zones de référence, hors zone, clic vers le document source |
| 4.3 Traitements et événements | ✅ | Ordonnances : 133/133 traitements (molécule + durée) sur le jeu de dev ; comptes rendus : 41/42 événements ; validation par le médecin, saisie manuelle |
| 4.4 Frise et annotations | ✅ | Barres de traitement (long cours / court), exacerbations, hospitalisations, changements de traitement, radiographies, curseur commun |
| 4.5 Tendances | ✅ | Theil-Sen, variation, qualification par seuil cliniquement significatif |
| 4.6 Alertes | ✅ | 4 types de règles, source et valeurs citées, actuelles / historique, acquittement conservé, réservées à une pathologie si besoin (référentiel v0.2.0) |
| 4.7 Cas de référence | ✅ | 24 cas de référence tendances/alertes, 100 % de concordance |

Tests : 120 tests backend verts. Trois patients chargés par l'API (A01 BPCO, B01 pneumonie, C01 fibrose) avec `scripts/load_synthetic_patient.py`.

## Phase 5 : Module C, imagerie

| Étape | Statut | Notes |
|---|---|---|
| 5.1 Service d'inférence | ✅ | TorchXRayVision CPU, 10 pathologies, contrôles de qualité (couleur, résolution, proportions, contraste), modèle et version stockés ; analyse au dépôt, 1,9 s par radio dans Docker |
| 5.2 Grad-CAM et incertitude | ✅ | Carte par pathologie à la demande (mise en cache), écart-type sur 7 variantes |
| 5.3 Liste et visionneuse | ✅ | Vignettes R1…Rn, côte à côte / superposition avec opacité, zoom et déplacement synchronisés, carte superposable, vue face/profil, lecture du médecin |
| 5.4 Courbe des scores | ✅ | Scores IA ± incertitude sur l'axe commun de l'écran d'évolution, seuil du modèle 0,50, mention « indicatif, non diagnostique » |
| 5.5 Évaluation imagerie | ✅ | RSNA 1 500 images, `evaluation/results/imaging_rsna.json`. AUC externe (`-chex`) : opacité 0,794 [0,773–0,817], pneumonie 0,773 [0,750–0,797], consolidation 0,792 [0,770–0,815]. AUC interne (`-all`, optimiste, RSNA vu à l'entraînement) : 0,877 / 0,827 / 0,854. Écart F/H ≤ 0,02 ; 18-40 ans meilleurs (+0,03 à +0,04) |

Constats pour la fiche du modèle : au seuil 0,50, le score « Lung Opacity » est très sensible et peu spécifique (interne : Se 0,96, Sp 0,55), le score « Pneumonia » l'inverse (Se 0,59, Sp 0,87) ; plusieurs scores se regroupent autour de 0,50 (seuil de calibration) ; le Grad-CAM porte parfois sur les bords de l'image ou le cou (raccourcis appris), d'où la légende obligatoire.

Tests : 125 tests backend verts (faux modèle pour les tests d'API, vrai modèle testé si ses poids sont présents).

## Phase 6 : Module E, fiche pré-consultation et intégration

| Étape | Statut | Notes |
|---|---|---|
| 6.1 Dossier de faits | ✅ | `services/facts.py`, `GET /api/patients/{id}/facts` : dernières valeurs (ancienneté, variation depuis la mesure précédente), tendances 12 mois, alertes actuelles, traitements en cours et dernier changement, 2 dernières radios de face (variation ± marge T29), points à aborder. Chaque fait cite mesure / document. JSON d'A01 relu contre `demo-scenario.md` : concordant |
| 6.2 Fiche gabarit et PDF | ✅ | Gabarit Jinja2 (`app/templates/sheet.html`) -> PDF A4 par le moteur HTML de PyMuPDF (T32) ; sources numérotées dans l'ordre de citation, bandeau, date, versions ; onglet « Fiche » (aperçu isolé, téléchargement), fiche conservée (`consultation_sheets`, faits + HTML + PDF). Une page pour A01, B01 et C01 ; vérifié dans le navigateur |
| 6.3 Reformulation LLM et vérificateur | ✅ | Rédaction assistée évaluée puis retirée de l'interface (T35) ; accessible par l'API (`assisted=true`) pour reproduire les mesures. Entrée du LLM : faits saillants en phrases (sans nom ni identifiant). Vérificateur : nombres (arrondi à la précision écrite), unités, dates, tendances et position par rapport à la norme concordantes, radios dans la marge non décrites comme une évolution, sigles développés, texte tronqué, mots interdits, maladies absentes ; 2 échecs => gabarit. 100 % des fiches livrées vérifiées ou par gabarit. Mesure (llama3.2:3b, CPU, 3 patients × 2 séries) : 1/6 puis 0/6 synthèses acceptées, 17 à 75 s par essai, 37 à 129 s par fiche (budget D10 : 60 s) ; erreurs du modèle : « souffre de », sigles mal développés, tendances contraires, « augmentation » radiographique dans la marge. Décision T35 : option retirée de l'interface (code, tests et mesures conservés pour le rapport) |
| 6.4 Garde-fous | ✅ | Revue des écrans dans le navigateur : bandeau présent sur les 9 écrans (connexion, patients, évolution, radiographies, documents, à valider, validation, fiche, 404) ; mentions propres à chaque sortie IA (carte d'attention, scores radio avec modèle et version, courbe « indicatif, non diagnostique », fiche). Journal : table d'audit (lectures, décisions, générations de fiche avec mode), essais du LLM conservés avec la fiche, modèle LLM noté sur le document quand il propose un type ou des valeurs. Questions libres : aucune entrée de texte vers le LLM (3 points d'entrée : classification, extraction de secours, fiche) ; le refus hors dossier s'appliquera à l'assistant F-E4 (phase 7) |
| 6.5 Tableau de bord unique | ✅ | Onglet Évolution = tableau de bord : profil et alertes (colonne), courbes et frise, radiographies comparées (2 dernières de face, score suivi, marge T29, lien vers la visionneuse), fiche pré-consultation intégrée. Démo : 2 changements de page (validation puis retour). Vérifié à 1400 px et 390 px, sans défilement horizontal |

Tests : 133 tests backend verts.

## Phases 7 à 10

⬜ Non commencées.

## Blocages

- Aucun.
