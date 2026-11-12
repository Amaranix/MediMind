# Rapport d'évaluation (phase 9)

> Évaluation finale du 12/11/2026. **Règle** : les 6 patients de test (`synthetic/splits.json`) et le gabarit de laboratoire T4 n'ont jamais servi au développement ; ils sont évalués une seule fois, ici. Chaque chiffre renvoie à un fichier de `evaluation/results/` et à la commande qui le produit.

## 1. Cibles et résultats

| Composant | Cible (PLAN §9) | Résultat | Statut |
|---|---|---|---|
| Extraction, PDF natifs | F1 ≥ 0,95 | **1,000** (353 valeurs) | ✅ |
| Extraction, scans | F1 ≥ 0,85 | **0,880** (scans PDF) ; photos 0,941 | ✅ |
| Extraction, gabarit tenu à l'écart | écart rapporté | T4 : **0,957** contre 1,000 / 1,000 / 0,968 pour T1 / T2 / T3 | ✅ rapporté |
| Normalisation (paramètre + unité + contexte) | ≥ 95 % | **98,3 %** des valeurs extraites exactes (précision, 462 / 470) | ✅ |
| Tendances et alertes | 100 % | **24 / 24** cas de référence ; alertes du patient A01 conformes au scénario | ✅ |
| Imagerie | AUC pneumonie ≥ 0,75 en externe | **0,773** [0,750 ; 0,797] | ✅ |
| Fiche | 100 % des nombres vérifiés | **100 %** (gabarit) ; ablation ci-dessous | ✅ |
| Assistant (RAG) | ≥ 85 % fidélité et citations | **60 / 60** réponses justes, **60 / 60** citations complètes | ✅ |
| Utilité (proxy) | temps −50 %, SUS ≥ 70 | *À mesurer* (protocole `docs/usability-protocol.md`) | ⏳ |
| Ablation de l'extraction | comparaison rapportée | règles 0,978 ; hybride 0,978 ; LLM seul 0,082 | ✅ rapporté |

## 2. Extraction (9.1)

Commande : `cd backend && TESSERACT_CMD=... .venv/Scripts/python ../evaluation/run_extraction_eval.py --split test` → `extraction_test.json`. Règle de correction : paramètre, contexte (pré/post-BD, repos, air ambiant) et valeur canonique concordants (tolérance 0,5 %).

| Partie | Documents | P | R | F1 |
|---|---|---|---|---|
| **Test, global** | 137 | 0,983 | 0,965 | **0,974** |
| PDF natifs | | 1,000 | 1,000 | 1,000 |
| Scans PDF | | 0,928 | 0,837 | 0,880 |
| Photos | | 0,941 | 0,941 | 0,941 |
| Bilans / EFR / comptes rendus | | 0,973 / 1,000 / 1,000 | 0,970 / 0,944 / 1,000 | 0,971 / 0,971 / 1,000 |
| Développement, pour mémoire (`extraction_dev.json`) | 709 | | | natif 1,000 ; scans 0,936 ; photos 0,953 |

Classification du type : 100 %. Date d'examen : 100 %. Durée : 0,69 s par document en moyenne (3,6 s au plus).

**Lecture** : les erreurs se concentrent sur l'OCR des scans (15 valeurs manquées, 6 fausses), surtout des chiffres de numération (éosinophiles, lymphocytes, plaquettes) et des valeurs d'EFR (8 manquées). La baisse des scans entre développement (0,936) et test (0,880) montre la limite de l'OCR sur un gabarit jamais vu. Aucune erreur sur les PDF natifs. Toutes ces valeurs passent par la validation du médecin, où la confiance OCR (plafonnée à 0,9) impose une décision une par une.

## 3. Normalisation, tendances et alertes (9.2)

- **Normalisation** : 98,3 % des valeurs extraites ont le bon paramètre, la bonne unité canonique (conversions mg/dL → mg/L, µmol/L → mg/L...) et le bon contexte.
- **Tendances et alertes** : 24 cas de référence (`backend/tests/test_trends_alerts.py`) couvrant Theil-Sen et son insensibilité à une valeur aberrante, la qualification par seuil significatif, les 8 règles, le contexte de mesure exigé, les critères de progression réservés à la fibrose : **24 / 24**. Sur le patient de démonstration A01, les alertes actuelles et l'historique concordent avec `docs/demo-scenario.md`.

## 4. Imagerie (9.3)

Commande : `cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python ../evaluation/run_imaging_eval.py --dataset rsna` → `imaging_rsna.json`. 1 500 radiographies RSNA d'adultes (500 positives), AUC de Mann-Whitney, IC 95 % par bootstrap.

| Cible | Externe `-chex` | Interne `-all` (optimiste) |
|---|---|---|
| Opacité pulmonaire | 0,794 [0,773 ; 0,817] | 0,877 [0,859 ; 0,894] |
| **Pneumonie** | **0,773 [0,750 ; 0,797]** | 0,827 [0,806 ; 0,849] |
| Consolidation | 0,792 [0,770 ; 0,815] | 0,854 [0,835 ; 0,874] |

Sous-groupes (pneumonie, externe) : femmes 0,782, hommes 0,767 ; 18-40 ans 0,803, 41-60 ans 0,761, > 60 ans 0,763. Détails, seuils et limites : `docs/model-card.md`.

## 5. Fiche (9.4)

**Taux de nombres vérifiés** : la fiche livrée est produite par gabarit ; chaque chiffre est recopié du dossier de faits et porte sa source : 100 % par construction, contrôlé par le vérificateur (3 / 3 fiches acceptées, 0 nombre injustifié).

**Ablation** (`evaluation/run_sheet_ablation.py` → `sheet_ablation.json`), patients A01, B01, C01, `llama3.2:3b` local, 2 essais par condition, même vérificateur :

| Condition | Textes acceptés | Nombres et dates justifiés | Autres erreurs relevées | Durée moyenne |
|---|---|---|---|---|
| Gabarit (faits → texte par le code) | 3 / 3 | 10 / 10 (100 %) | 0 | instantané |
| LLM seul, sur le texte brut des documents | 0 / 6 | 7 / 33 (**21 %**) | 7 | 80 s |
| LLM sur les faits calculés (+ vérificateur) | 0 / 6 | 44 / 44 (**100 %**) | 16 | 43 s |

**Lecture** : sans faits calculés, le LLM invente ou déforme la plupart des nombres. Avec les faits, il ne se trompe plus sur les nombres, mais ses formulations restent fausses (« souffre de », sigles développés au hasard, « augmentation » d'un score resté dans la marge, tendance contraire aux faits, texte tronqué), d'où aucune synthèse acceptée. Mesure de la phase 6.3 sur les mêmes patients : 1 synthèse acceptée sur 12. Décision : rédaction par LLM retirée de l'application (T35).

## 6. Ablation de l'extraction (9.5)

Commande : `cd backend && .venv/Scripts/python ../evaluation/run_extraction_ablation.py --n 15` → `extraction_ablation.json`. 15 documents de test tirés au hasard (graine 42 ; bilans, EFR, comptes rendus ; PDF natifs, scans, photos), même règle de correction qu'en 9.1. Le mode « LLM seul » utilise le même texte (PDF ou OCR) et le même filtre que l'application (valeur présente mot pour mot, paramètre connu, normalisation).

| Mode | P | R | F1 | Type de document juste | Durée moyenne |
|---|---|---|---|---|---|
| Règles seules | 0,978 | 0,978 | **0,978** | 100 % | 0,2 s |
| Hybride (règles, LLM en repli) | 0,978 | 0,978 | **0,978** | 100 % | 0,2 s |
| LLM seul (`llama3.2:3b`) | 0,800 | 0,043 | **0,082** | 20 % | 62 s |

**Lecture** : le repli LLM ne s'est déclenché sur aucun de ces documents (les règles reconnaissaient tout), d'où des résultats identiques entre règles et hybride. Seul, le petit LLM local échoue : il se trompe de type de document (une EFR classée « bilan biologique ») et rend le plus souvent une liste de valeurs vide ; quelques appels atteignent la limite de 60 s. Ses rares valeurs sont justes (précision 0,80) parce que le filtre littéral écarte les inventions. Conclusion : sur des gabarits connus, les règles sont à la fois plus exactes et 300 fois plus rapides ; le LLM n'a sa place qu'en repli, pour un document qu'aucune règle ne reconnaît.

## 7. Assistant du dossier (9.6)

Commande : `cd backend && .venv/Scripts/python ../evaluation/run_assistant_eval.py --split dev|test` → `assistant_dev.json`, `assistant_test.json`.

| Partie | Questions | Réponses justes | Citations complètes |
|---|---|---|---|
| Développement | 50 | 50 | 50 |
| **Test** (jamais vues) | 10 | **10** | **10** |

Familles : valeur à une date (21 + 3), variation entre deux dates (10 + 2), comptes d'événements (3 + 1), traitements (17 + 1), normalisation de la CRP (2 + 3).

**Limite** : les données de chaque patient sont construites à partir de la vérité terrain (équivalent d'un dossier entièrement validé) ; l'évaluation porte sur la logique de réponse et de citation. Dans l'application, l'exactitude dépend aussi de l'extraction, d'où la validation obligatoire par le médecin. La recherche libre (passages) a été vérifiée sur A01 : passages pertinents pour 3 questions, refus pour 2 questions hors sujet ; seuil à marge étroite (0,83).

## 8. Utilité (9.7)

*À compléter après la séance (protocole écrit avant le test : `docs/usability-protocol.md`).* Rapporter : temps médian avec et sans outil, réduction, justesse dans chaque condition, SUS moyen et étendue, commentaires ; rappeler que l'évaluation est proxy et non clinique.

## 9. Performance (rappel de la phase 8)

`scripts/perf.py` sur une instance neuve : courbes 1 an 0,05 s (budget 2 s), PDF natif 1,6 s (30 s), scan 3,2 s (60 s), radiographie 3,2 s (5 s), fiche 0,06 s (5 s).

## 10. Causes des écarts et limites

- **Scans** : l'OCR reste le point faible (0,880) ; piste : modèles de compréhension de documents, prétraitement adaptatif.
- **Évaluation en partie circulaire** : générateur et règles conçus par la même équipe ; atténuée par le gabarit T4 et les patients de test tenus à l'écart, non supprimée.
- **Imagerie** : population d'entraînement et d'évaluation non marocaine ; pas d'évaluation de l'évolution entre deux clichés (aucune vérité terrain).
- **LLM local** : trop peu fiable pour rédiger ; sa place est limitée au repli de lecture, avec filtre littéral et validation.
- **Pas de clinicien** dans l'évaluation ; le test d'utilité est un proxy.
