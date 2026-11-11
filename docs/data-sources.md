# Sources de données et reproduction

Les images et les documents générés ne sont **pas** versionnés (`data/`, `synthetic/out/`). Tout se régénère avec les commandes ci-dessous. La vérité terrain (`synthetic/ground_truth/`), les splits et les questions sont versionnés.

## 1. NIH ChestX-ray14 (séries de radiographies)

- **Source** : NIH Clinical Center, via Kaggle `nih-chest-xrays/data` (licence indiquée par Kaggle : CC0-1.0).
- **Citation obligatoire** : Wang X, Peng Y, Lu L, Lu Z, Bagheri M, Summers RM. *ChestX-ray8: Hospital-scale Chest X-ray Database and Benchmarks on Weakly-Supervised Classification and Localization of Common Thorax Diseases.* IEEE CVPR 2017. Remerciements au NIH Clinical Center.
- **Sous-ensemble** : 60 patients (20 par profil BPCO / pneumonie / fibrose, 10 F / 10 H), adultes de 18 à 90 ans, vues de face, au moins 3 radios ; 327 images (128 Mo).
- **Limite connue** : étiquettes extraites automatiquement des comptes rendus (bruitées) ; dates réelles inconnues, remplacées par des dates synthétiques ordonnées selon `Follow-up #`.

```
python ml/scripts/select_nih_patients.py      # -> data/nih_subset/manifest.csv
python ml/scripts/download_nih_subset.py      # -> data/nih_subset/images/
```

## 2. RSNA Pneumonia Detection Challenge (évaluation de l'imagerie)

- **Source** : Radiological Society of North America, Kaggle `rsna-pneumonia-detection-challenge` (règles de la compétition à accepter sur Kaggle).
- **Citation** : Shih G, et al. *Augmenting the National Institutes of Health Chest Radiograph Dataset with Expert Annotations of Possible Pneumonia.* Radiology: Artificial Intelligence 2019;1(1):e180041.
- **Sous-ensemble** : 1 500 images adultes (500 « Lung Opacity », 1 000 autres), une image par patient.

```
python ml/scripts/prepare_rsna_subset.py      # -> data/rsna_subset/images/, labels.csv
```

## 3. Dossiers synthétiques

- 36 patients fictifs (12 par parcours A BPCO, B pneumonie, C fibrose), 846 documents : 493 PDF natifs, 112 PDF scannés, 74 photos JPG, 167 radiographies.
- 4 gabarits de laboratoire : T1, T2, T3 (développement), **T4 réservé aux patients de test** (décision D9).
- Split figé : 30 développement / 6 test (`synthetic/splits.json`) ; patient de démo **A01** (`docs/demo-scenario.md`).
- Chaque document porte la mention « Document fictif généré pour le projet MediMind ».
- Valeurs théoriques EFR : équations ECSC (Quanjer et al., Eur Respir J 1993).

```
python -m synthetic.generator --seed 42       # -> synthetic/out/, synthetic/ground_truth/, synthetic/splits.json
python -m synthetic.generator.questions       # -> evaluation/questions_60.jsonl
```

## Environnement

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-data.txt
.venv/Scripts/python -m playwright install chromium
```
Jeton Kaggle : `~/.kaggle/access_token` (jamais dans le dépôt).
