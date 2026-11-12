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
| T14 | 2026-11-11 | OCR : redressement automatique (profil de projection), filtre médian 3×3, seuil d'Otsu, Tesseract `fra` en `--psm 6` | Mesuré sur un scan de gabarit T3 : 9/9 valeurs lues contre 1/9 sans prétraitement, OCR 3 fois plus rapide |
| T15 | 2026-11-11 | Confiance d'une valeur lue par OCR plafonnée à 0,9 ; validation groupée réservée aux valeurs de confiance ≥ 0,95 sans signalement | Les valeurs scannées sont toujours validées une par une par le médecin |
| T16 | 2026-11-11 | Nombres situés dans une plage de référence (entre parenthèses, autour d'un « - » ou « à ») jamais pris pour une valeur ; fusion des milliers seulement si une unité suit | Évite qu'une valeur illisible soit remplacée par une borne de référence (erreur dangereuse détectée en évaluation) |
| T17 | 2026-11-11 | Date d'examen : saisie du médecin > date lue dans le document > date de dépôt (avec avertissement) ; la date de naissance est exclue | Fiabilité de l'axe temporel des courbes |
| T18 | 2026-11-11 | Évaluation de l'extraction sans repli LLM par défaut (`--llm` pour l'activer) | Mesurer d'abord la chaîne déterministe ; le LLM n'est qu'un secours |
| T19 | 2026-11-11 | Courbes en SVG maison (React) plutôt que Recharts | Un seul axe du temps partagé par toutes les courbes, la frise et le curseur (idée directrice des maquettes), difficile à obtenir avec des graphiques indépendants |
| T20 | 2026-11-11 | Fiche patient : pathologies suivies (BPCO, fibrose, pneumonie) ; une règle peut être réservée à certaines pathologies (`conditions`). PPF_FVC et PPF_DLCO réservées à la fibrose. Référentiel v0.2.0 | Le critère ATS/ERS/JRS/ALAT 2022 se déclenchait chez un patient BPCO dont la CVF baisse : alerte hors de son contexte clinique |
| T21 | 2026-11-11 | Alerte « actuelle » si elle porte sur la donnée la plus récente du paramètre, sinon historique ; recalcul à chaque décision du médecin, acquittements conservés | Le panneau ne montre que ce qui concerne l'état présent ; l'historique reste consultable |
| T22 | 2026-11-11 | Courbes et tendances de spirométrie : mesures pré-bronchodilatateur exclues | On suit le post-BD (ou la mesure sans test de réversibilité) |
| T23 | 2026-11-11 | Traitement au long cours : continue tant que les ordonnances de fond le renouvellent, s'arrête à la première qui ne le contient plus ; changements de traitement déduits de deux ordonnances de fond successives | Frise fidèle sans saisir de date d'arrêt |
| T24 | 2026-11-11 | `scripts/load_synthetic_patient.py` charge un patient synthétique par l'API et simule les décisions du médecin à partir de la vérité terrain | Démo réaliste et test de bout en bout de la chaîne |
| T25 | 2026-11-11 | Imagerie : TorchXRayVision `densenet121-res224-all` sur CPU (PyTorch CPU), poids intégrés à l'image Docker, préchargés au démarrage | 0,24 s par inférence ; démonstration hors ligne |
| T26 | 2026-11-11 | Incertitude : écart-type des scores sur 7 variantes de l'image (rotation ±4°, décalage, contraste), appliquées après un prétraitement unique en 224×224 | Analyse complète en 1,9 s (contre 4,9 s en prétraitant chaque variante) |
| T27 | 2026-11-11 | Grad-CAM codé à la main (fin du réseau recalculée sans ReLU « en place ») ; carte transparente sous 25 % ; légende « zone d'attention, pas une localisation de lésion » | Le ReLU en place de TorchXRayVision annulait les gradients ; une bibliothèque de plus n'était pas nécessaire |
| T28 | 2026-11-11 | 10 pathologies affichées sur 18 ; score IA suivi par défaut selon la pathologie (BPCO : emphysème, fibrose : fibrose, pneumonie : consolidation) ; vue de profil déclarée par le médecin exclue des courbes et comparaisons | Pertinence pneumologique, lisibilité |
| T29 | 2026-11-11 | Variation entre deux radiographies jugée « dans la marge d'incertitude » si |Δ| ≤ 2·√(σ₁²+σ₂²) + 0,02 ; aucun verdict d'évolution produit par l'IA (D5) | Ne pas présenter du bruit comme une évolution |
| T30 | 2026-11-11 | Évaluation imagerie en deux mesures : poids `-all` (interne, optimiste, vus à l'entraînement : NIH, RSNA…) et poids `-chex` sur RSNA (externe) ; AUC Mann-Whitney + IC95 par bootstrap, par sexe et âge | Rendre visible la fuite de données plutôt que la cacher |
| T31 | 2026-11-12 | Dossier de faits : motif = pathologies suivies (« Suivi : BPCO ») faute de champ motif ; variation « depuis la dernière visite » = écart avec la mesure précédente du paramètre ; tendances sur les 12 mois précédant la dernière donnée ; points à aborder = alertes actuelles non acquittées + valeurs en attente de validation | Pas de notion de visite en base ; une valeur non validée ne doit pas disparaître sans le dire |
| T32 | 2026-11-12 | PDF de la fiche rendu par le moteur HTML de PyMuPDF (`Story`) au lieu de WeasyPrint ; valeurs de plus de 6 mois regroupées sur une ligne ; sources sur un paragraphe ; nom affiché « Prénom N. » | PyMuPDF déjà présent, pas de bibliothèques système (Pango) ; la fiche d'A01 dépassait une page avec une liste numérotée |
| T33 | 2026-11-12 | Rédaction assistée : texte libre (sans format JSON imposé, qui faisait boucler llama3.2:3b), 300 tokens max, délai de 90 s par essai ; entrée réduite aux faits saillants ; vérificateur étendu au-delà des nombres (unités, tendances, zone de référence, radios, sigles) ; option marquée « expérimental », gabarit par défaut (D4) | Mesuré : un contrôle des seuls nombres laissait passer « BPCO depuis 40 ans » (40 paquets-années) et des tendances contraires aux faits |
