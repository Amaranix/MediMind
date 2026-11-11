# User stories : pneumologue (Dr P.)

> Format : En tant que … je veux … afin de … · Fonctionnalité(s) · Tranche · Critère d'acceptation.

| # | Story | F-xx | Tranche | Critère d'acceptation |
|---|---|---|---|---|
| US1 | En tant que pneumologue, je veux me connecter de façon sécurisée afin que seuls mes patients me soient accessibles. | F-A1 | T1 | Un autre médecin reçoit 404 sur mes patients |
| US2 | En tant que pneumologue, je veux créer la fiche d'un patient adulte (âge, sexe, taille, tabagisme, antécédents, allergies, traitements de fond) afin d'avoir son contexte. | F-A2 | T1 | Création refusée si < 18 ans |
| US3 | En tant que pneumologue, je veux déposer plusieurs documents à la fois (PDF, photos, scans) avec leur date d'examen afin de ne pas les traiter un par un. | F-A3 | T1 | 5 fichiers ⇒ 5 traitements suivis, doublon signalé |
| US4 | En tant que pneumologue, je veux voir l'état du traitement de chaque document afin de savoir quand je peux le valider. | F-03 | T1 | Statut en file / en cours / terminé / échec, relance possible |
| US5 | En tant que pneumologue, je veux voir chaque valeur extraite à côté de la zone du document d'où elle vient afin de la vérifier d'un coup d'œil. | F-A4, F-A6, F-A8 | T1 | Survol d'une valeur ⇒ zone surlignée |
| US6 | En tant que pneumologue, je veux valider, corriger ou rejeter une valeur en un clic afin que seules des données fiables alimentent le suivi. | F-A8 | T1 | Statut + auteur + horodatage enregistrés |
| US7 | En tant que pneumologue, je veux que « VEMS », « FEV1 » ou « mL » / « L » soient reconnus comme équivalents afin de comparer des laboratoires différents. | F-A7 | T1 | Valeurs ramenées à l'unité canonique |
| US8 | En tant que pneumologue, je veux afficher l'évolution des paramètres sur 3 mois, 6 mois, 1 an ou une période libre afin de voir si le patient va mieux. | F-B1, F-B2 | T1 | Courbes 1 an affichées en < 2 s |
| US9 | En tant que pneumologue, je veux voir les traitements, exacerbations, hospitalisations et radios sur le même axe que les courbes afin de relier causes et effets. | F-B3, F-D1, F-D2, F-D4 | T2 | Frise et courbes alignées |
| US10 | En tant que pneumologue, je veux une tendance chiffrée (pente, variation) et qualifiée afin de ne pas l'estimer de tête. | F-B4 | T2 | Pente annualisée + « stable / amélioration / dégradation » |
| US11 | En tant que pneumologue, je veux des alertes qui citent la règle, la recommandation et les valeurs déclenchantes afin de juger leur pertinence. | F-B5 | T2 | Chaque alerte : règle + source + valeurs ; acquittement |
| US12 | En tant que pneumologue, je veux voir la liste des radios d'un patient avec les scores IA par pathologie et la zone d'attention du modèle afin d'orienter ma lecture. | F-C1, F-C2, F-C3 | T1/T2 | Scores + incertitude + Grad-CAM légendé |
| US13 | En tant que pneumologue, je veux comparer deux radios côte à côte avec un zoom synchronisé afin de juger l'évolution moi-même. | F-C4 | T2 | Zoom et déplacement synchronisés, superposition |
| US14 | En tant que pneumologue, je veux voir les scores IA dans le temps alignés sur la biologie afin de croiser imagerie et analyses. | F-C5 | T2 | Même axe temporel que les courbes |
| US15 | En tant que pneumologue, je veux une fiche pré-consultation d'une page dont chaque chiffre est vérifié et relié à sa source afin de préparer ma consultation en une minute. | F-E1, F-E2, F-E3 | T2 | 1 page PDF, 100 % des nombres vérifiés |
| US16 | En tant que pneumologue, je veux poser une question sur le dossier et obtenir une réponse citée afin de retrouver une information rapidement. | F-E4 | T3 | Réponse avec document et date, refus hors dossier |
| US17 | En tant qu'administrateur, je veux créer et désactiver les comptes médecins sans accéder aux données patient afin de respecter la confidentialité. | F-A1 | T1 | Aucun endpoint patient accessible à l'admin |
| US18 | En tant que pneumologue, je veux supprimer définitivement le dossier d'un patient afin de respecter son droit à l'effacement. | Sécurité | T2 | Base + fichiers + index supprimés, action tracée |
