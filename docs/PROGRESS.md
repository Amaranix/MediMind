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
| 1.2 Sous-ensemble RSNA | 🟨 | Script prêt (`prepare_rsna_subset.py`). Bloqué : règles de la compétition à accepter sur Kaggle |
| 1.3 Générateur synthétique | ✅ | 36 patients, 846 documents (493 PDF natifs, 112 scans PDF, 74 photos, 167 radios), 4 gabarits (T4 test), vérité terrain contrôlée contre le texte des PDF |
| 1.4 Questions et démo | ✅ | `evaluation/questions_60.jsonl`, `docs/demo-scenario.md` (patient A01) |

## Phases 2 à 10

⬜ Non commencées.

## Blocages

- Aucun.
