# Scénario de démonstration : patient A01

> Patient fictif généré par `python -m synthetic.generator --seed 42`. Vérité terrain : `synthetic/ground_truth/A01.json`. Documents : `synthetic/out/A01/`.

## Le patient

**Karim Alaoui**, homme, né le 14/03/1962 (64 ans), 172 cm, 40 paquets-années. BPCO suivie au Cabinet de Pneumologie Les Orangers (Dr Nadia Berrada). Suivi du 20/11/2025 au 05/11/2026.

| Date | Événement | Ce que l'application doit montrer |
|---|---|---|
| 20/11/2025 | Première consultation : EFR, bilan (gabarit T1), radio R1, ordonnance tiotropium + salbutamol | VEMS post-BD 1,62 L (53 % th) ; VEMS/CVF post-BD 46 % |
| 15/01/2026 | Suivi : EFR, bilan (T3) | VEMS post-BD 1,60 L |
| 10/02/2026 | **Exacerbation** : bilan **scanné** (T3, CRP 10,62 mg/dL = 106 mg/L), compte rendu (SpO2 91 %), antibiotique + prednisolone | Pic de CRP, SpO2 < 92 % ; démonstration de l'OCR et de la conversion mg/dL → mg/L |
| 11 au 14/02/2026 | **Hospitalisation**, gaz du sang à l'admission ; radio R2 le 11/02 | Barre d'hospitalisation sur la frise |
| 02/03/2026 | **Changement de traitement** : ajout salmétérol/fluticasone | Début de la barre de traitement, annotation sur les courbes |
| 15/05/2026 | Suivi : EFR, bilan, radio R3 | VEMS post-BD 1,51 L |
| 20/08/2026 | **Exacerbation** n° 2 (CRP 103 mg/L, SpO2 91 %) ; radio R4 le 21/08 | Deuxième pic de CRP |
| 17/09/2026 | Visite de suivi reportée à J28 après l'exacerbation : EFR, bilan | VEMS post-BD 1,54 L |
| 05/11/2026 | Dernière visite : EFR, bilan (T3), compte rendu, radio R5 | VEMS post-BD 1,50 L (49 % th) |

## Alertes attendues

| Règle | Déclenchement attendu |
|---|---|
| OBS_FEV1_FVC | Oui : VEMS/CVF post-BD < 0,70 à chaque EFR |
| FEV1_DECLINE | Oui : 1,62 L → 1,50 L, soit −120 mL sur 12 mois (pente Theil-Sen à confirmer par le moteur) |
| CRP_RISE | Oui : 10/02/2026 et 20/08/2026 |
| SPO2_LOW | Oui : 91 % au repos en air ambiant le 10/02 et le 20/08 |
| EOS_HIGH | Oui : éosinophiles ≥ 0,3 G/L à plusieurs bilans |
| PPF_FVC, PPF_DLCO, CRP_NOT_NORMALIZED | Non |

## Déroulé en direct (environ 5 minutes)

1. **Connexion** avec le compte de démonstration (créé par `scripts/seed_demo.py`, phase 8).
2. **Liste des patients** : Karim Alaoui apparaît avec ses alertes ouvertes.
3. **Dépôt** des documents du 05/11/2026 (EFR, bilan, compte rendu, radio R5). Les documents antérieurs sont déjà chargés et validés par le seed, sauf le **bilan scanné du 10/02/2026**, laissé « à valider ».
4. **Validation** : ouvrir le bilan scanné du 10/02/2026, montrer la confiance OCR et la conversion d'unité, corriger si besoin, valider. Puis valider les documents du 05/11.
5. **Évolution** : période 6 mois puis 1 an ; lire les valeurs avec le curseur ; montrer les deux pics de CRP alignés sur les exacerbations, l'hospitalisation et l'ajout de salmétérol/fluticasone sur la frise.
6. **Alertes** : ouvrir FEV1_DECLINE (règle, source ERS/ATS 2022, valeurs déclenchantes) puis l'acquitter.
7. **Radiographies** : comparer R4 (21/08/2026) et R5 (05/11/2026) côte à côte puis en superposition ; activer la zone d'attention ; lire la variation des scores avec l'incertitude.
8. **Fiche pré-consultation** : générer, montrer le panneau de contrôle (nombres vérifiés), télécharger le PDF.

## Plan B

Vidéo de démonstration hors ligne (phase 10) et base pré-remplie avec toutes les étapes validées.
