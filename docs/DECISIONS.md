# Décisions d'architecture et de périmètre

> Format : une entrée par décision. Statut : `acceptée` / `refusée` / `remplacée par Dxx`.
> Toute modification d'un seuil clinique, d'un dataset ou d'une priorité doit être ajoutée ici.

## Écarts au cahier des charges, validés par l'encadrant (Pr A. Chergui), 2026-11-11

| # | Décision | Raison | Statut |
|---|---|---|---|
| D1 | Patients adultes uniquement (≥ 18 ans, refus à la saisie) | Utilisateur = pneumologue adulte ; modèles et normes adultes | acceptée |
| D2 | Dataset Kermany (pédiatrique) retiré ; sous-ensemble NIH ChestX-ray14 (séries) + RSNA Pneumonia (évaluation) | Kermany pédiatrique, sans série, val inutilisable ; RSNA relu par des radiologues | acceptée |
| D3 | LLM local uniquement (Ollama), API Groq retirée | Données de santé ne quittent pas la machine (loi 09-08) | acceptée |
| D4 | Fiche pré-consultation par gabarit déterministe par défaut ; reformulation LLM optionnelle + vérificateur | Pas de GPU ; zéro hallucination | acceptée |
| D5 | F-C6 = « variation des scores entre deux radios » + incertitude ; pas de verdict IA ; cible de 70 % supprimée | Pas de vérité terrain d'évolution | acceptée |
| D6 | F-D3 (interactions médicamenteuses) et F-E5 (brouillon de compte rendu) retirées | Hors fil conducteur / risque clinique | acceptée |
| D7 | Règles d'alerte corrigées et sourcées (PLAN §5) | Contexte post-BD, fatigue d'alerte, critère PPF 1/3 | acceptée |
| D8 | F-A8 (validation) et F-A9 (audit) dès la tranche T1 | Socle de la confiance et de la traçabilité | acceptée |
| D9 | 4 gabarits de laboratoire, dont 1 tenu à l'écart pour le test | Limiter l'évaluation circulaire | acceptée |
| D10 | Budget de la fiche avec LLM porté à 60 s (gabarit < 5 s) | Matériel CPU sans GPU | acceptée |
| D11 | Pas d'affinage du modèle d'imagerie | Pas de GPU ; pré-entraîné suffisant pour un démonstrateur | acceptée |

## Décisions techniques

| # | Date | Décision | Raison |
|---|---|---|---|
| T1 | 2026-11-11 | Le dépôt Git = dossier racine du projet ; CdC déplacé en `docs/CDC.pdf`, ancien plan archivé dans `docs/archive/` | Un seul dépôt, structure du PLAN §7.4 |
| T2 | 2026-11-11 | Ollama exécuté sur l'hôte Windows, accédé depuis Docker via `host.docker.internal:11434` ; modèle par défaut `llama3.2:3b` | Déjà installé ; plus simple sans GPU |
| T3 | 2026-11-11 | Unités canoniques du référentiel adaptées aux laboratoires marocains francophones (CRP mg/L, créatinine mg/L, Hb g/dL, cellules en G/L, gaz du sang en mmHg) | Correspond aux comptes rendus rencontrés au Maroc |
| T4 | 2026-11-11 | Conception UI guidée par la skill `frontend-design` | Demande du binôme |
| T5 | 2026-11-11 | Documents synthétiques rendus en PDF par Chromium (Playwright) ; scans simulés avec PyMuPDF + Pillow (rotation ±1,5°, flou, bruit, JPEG) | Rendu CSS fidèle, gabarits variés ; une rotation de ±3° décalait les lignes des gabarits à points de conduite |
| T6 | 2026-11-11 | Tous les documents synthétiques datés au plus tard du 05/11/2026 ; patient de démo A01 (Karim Alaoui) suivi du 20/11/2025 au 05/11/2026 | Dossiers « passés » au moment de la démonstration |
| T7 | 2026-11-11 | Parcours A : visite programmée reportée à J28 si elle tombe dans les 4 semaines suivant une exacerbation | Pas d'EFR pendant une exacerbation ; cohérence CRP/EFR |
| T8 | 2026-11-11 | Parcours B : demi-vie de la CRP 1,6 à 2,4 jours ; parcours C : patients stables à moins de 2,5 points de CVF/an | Séparer nettement les cas qui doivent déclencher une alerte de ceux qui ne le doivent pas |
| T9 | 2026-11-11 | Nom et prénom du patient stockés en base | Nécessaires à l'usage (liste, en-têtes) ; aucune donnée ne sort de la machine (LLM local) |
| T10 | 2026-11-11 | Identifiants de connexion au format e-mail validés par expression régulière (domaines internes `.local` acceptés) | La validation stricte refusait `.local` ; aucun e-mail n'est envoyé |
| T11 | 2026-11-11 | Session : jeton d'accès 15 min en mémoire, jeton de rafraîchissement 7 j en cookie httpOnly/Secure/SameSite=Strict limité à `/api/auth` | Jeton non lisible par le JavaScript ; session restaurée au rechargement |
| T12 | 2026-11-11 | HTTPS local par Caddy (`tls internal`) sur le port 8443 | Pas de droits administrateur ni de conflit avec 443 ; certificat local à accepter une fois |
| T13 | 2026-11-11 | RSNA : archive complète téléchargée en une requête puis lecture dans le zip | Le téléchargement image par image déclenche la limitation de débit de Kaggle ; 572 images disponibles en attendant |
