# Protocole du test d'utilité (étape 9.7)

> Évaluation **proxy, non clinique** : les participants ne sont pas des pneumologues et les dossiers sont fictifs. Le protocole est fixé avant le test ; il ne change pas en cours de séance.

## Objectif et cibles (PLAN §9)

- **Temps** : répondre à 5 questions sur un dossier avec MediMind en moins de la moitié du temps nécessaire avec les seuls documents (cible : −50 %).
- **Satisfaction** : score SUS moyen ≥ 70.

## Participants

L'encadrant et 3 à 5 étudiants (≥ 4 personnes au total). Aucune donnée personnelle n'est recueillie : un numéro (P1, P2...) par participant.

## Matériel

- Instance préparée par `scripts/seed_demo.py` sur le poste du binôme, la visite du 05/11/2026 de Karim Alaoui (A01) déposée et validée **avant** la séance.
- **Sans outil** : les 31 fichiers d'A01 (`synthetic/out/A01/`), imprimés ou ouverts dans un dossier, rangés par date comme dans un dossier papier.
- **Avec outil** : MediMind, compte `berrada@medimind.local`, patient Karim Alaoui (A01).
- Un chronomètre, la fiche de recueil ci-dessous, le questionnaire SUS.

## Questions (patient A01, Karim Alaoui)

Deux séries équivalentes pour qu'un participant ne réponde jamais deux fois à la même question.

| # | Série 1 | Réponse attendue | Série 2 | Réponse attendue |
|---|---|---|---|---|
| 1 | Quel était le VEMS post-BD le 15/05/2026 ? | 1,51 L | Quel était le VEMS post-BD le 17/09/2026 ? | 1,54 L |
| 2 | Combien d'exacerbations sur la période suivie ? | 2 (10/02 et 20/08/2026) | Combien d'hospitalisations sur la période suivie ? | 1 (11 au 14/02/2026) |
| 3 | De combien le VEMS a-t-il varié entre le 20/11/2025 et le 05/11/2026 ? | −120 mL | De combien la CVF a-t-elle varié entre le 20/11/2025 et le 05/11/2026 ? | −500 mL |
| 4 | Quand le salmétérol/fluticasone a-t-il été ajouté ? | 02/03/2026 | Depuis quand le tiotropium est-il prescrit ? | 20/11/2025 |
| 5 | Quelle était la CRP lors de l'exacerbation du 20/08/2026 ? | 103,4 mg/L | Quelle était la CRP lors de l'exacerbation du 10/02/2026 ? | 106,2 mg/L |

*Réponses attendues vérifiées le 12/11/2026 sur la vérité terrain d'A01 ; à revérifier dans l'instance de la séance (patient validé) avant le test.*

## Déroulement (environ 20 min par participant)

1. **Accueil (2 min)** : lecture du texte d'introduction ci-dessous ; aucune autre explication.
2. **Prise en main (3 min)** : démonstration standard de MediMind (tableau de bord, onglet Assistant), identique pour tous.
3. **Condition A puis B** : la moitié des participants commence par « sans outil », l'autre moitié par « avec outil » (ordre contrebalancé : P1, P3, P5 commencent sans outil). Série 1 pour la première condition, série 2 pour la seconde.
4. Pour chaque question : le chronomètre part à la lecture de la question et s'arrête quand le participant annonce sa réponse. Limite de 3 min par question (au-delà : « non trouvé », temps compté 180 s).
5. **Questionnaire SUS (3 min)** juste après la condition « avec outil ».
6. **Commentaires libres (2 min)** : une remarque positive, une négative.

Texte d'introduction : « Vous allez répondre à des questions sur le dossier d'un patient fictif suivi pour une BPCO, une fois avec les documents seuls, une fois avec l'application. Nous mesurons le temps et la justesse, pas vos connaissances médicales. »

## Fiche de recueil (une par participant)

| Participant | Ordre | Condition | Q1 (s / juste ?) | Q2 | Q3 | Q4 | Q5 | Total (s) | Réponses justes |
|---|---|---|---|---|---|---|---|---|---|
| P1 | A puis B | Sans outil (série 1) | | | | | | | /5 |
| P1 | A puis B | Avec outil (série 2) | | | | | | | /5 |

## Questionnaire SUS (System Usability Scale, version française)

Réponses de 1 (pas du tout d'accord) à 5 (tout à fait d'accord).

1. Je pense que j'aimerais utiliser cette application fréquemment.
2. J'ai trouvé l'application inutilement complexe.
3. J'ai trouvé l'application facile à utiliser.
4. Je pense que j'aurais besoin de l'aide d'une personne technique pour pouvoir utiliser cette application.
5. J'ai trouvé que les différentes fonctions de l'application étaient bien intégrées.
6. J'ai trouvé qu'il y avait trop d'incohérences dans l'application.
7. J'imagine que la plupart des gens apprendraient très rapidement à utiliser cette application.
8. J'ai trouvé l'application très lourde à utiliser.
9. Je me suis senti(e) très en confiance en utilisant l'application.
10. J'ai dû apprendre beaucoup de choses avant de pouvoir utiliser cette application.

**Calcul** : questions impaires : (réponse − 1) ; questions paires : (5 − réponse) ; somme × 2,5 = score sur 100.

## Analyse

- Temps total médian avec et sans outil, réduction = 1 − (avec / sans) ; justesse des réponses dans chaque condition.
- SUS moyen et étendue ; comparaison à la cible 70.
- Les résultats et les commentaires vont dans `docs/evaluation-report.md` (section Utilité), avec la limite : participants non cliniciens, effectif faible, questions factuelles.
