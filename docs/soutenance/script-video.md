# Script de la vidéo de démonstration (étape 10.4)

**Durée visée** : 4 min 30. **Outil** : OBS Studio, 1920 × 1080, navigateur en plein écran (zoom 110 %). **Sous-titres** : le texte « Voix » ci-dessous, à importer en .srt.
**Préparation** : instance neuve + `python scripts/seed_demo.py` ; documents du 05/11/2026 dans un dossier ouvert à côté (`synthetic/out/A01/`) ; Ollama inutile pour ce scénario.

| # | Temps | À l'écran | Voix |
|---|---|---|---|
| 1 | 0:00-0:20 | Page de connexion, puis bandeau « Aide à la décision » | « MediMind aide un pneumologue à suivre ses patients respiratoires à partir de leurs documents. C'est un démonstrateur de recherche : l'IA ne pose jamais de diagnostic, et toutes les données sont fictives. » |
| 2 | 0:20-0:35 | Connexion `berrada@medimind.local`, liste des patients | « Le Dr Berrada suit trois patients fictifs. Ouvrons le dossier de Karim Alaoui, 64 ans, suivi pour une BPCO. » |
| 3 | 0:35-1:05 | Onglet Documents : glisser les 4 fichiers du 05/11/2026, saisir la date 05/11/2026, Déposer ; la liste montre « Lecture en cours » puis les types détectés | « Il revient de sa visite du 5 novembre avec une EFR, un bilan, un compte rendu et une radiographie. On les dépose tels quels : l'application détecte le type de chaque document et lit les valeurs, y compris sur les scans, grâce à l'OCR. » |
| 4 | 1:05-1:45 | À valider : ouvrir le bilan scanné du 10/02/2026 ; montrer les zones surlignées, la confiance OCR, la conversion mg/dL → mg/L ; valider au clavier ; puis valider l'EFR du 05/11 (« Valider les valeurs sûres ») | « Rien n'entre dans le dossier sans le médecin. Chaque valeur est montrée à l'endroit où elle a été lue, avec sa confiance. Ici, la CRP du laboratoire est en mg/dL : elle est convertie, et le médecin valide ou corrige. » |
| 5 | 1:45-2:30 | Onglet Évolution : période 1 an, curseur sur les deux pics de CRP alignés sur les exacerbations, barre de salmétérol/fluticasone, tableau dernière / précédente / variation | « Les valeurs validées s'alignent sur un même axe du temps : les deux pics de CRP tombent sur les deux exacerbations, et l'on voit le renforcement du traitement en mars. Le VEMS baisse de 120 mL sur l'année. » |
| 6 | 2:30-2:55 | Colonne Alertes : ouvrir « Déclin du VEMS », montrer la règle et la source ERS/ATS 2022, acquitter | « Les alertes viennent de règles publiées, jamais d'un modèle : chacune cite sa source et les valeurs qui la déclenchent. Le médecin les acquitte. » |
| 7 | 2:55-3:35 | Onglet Radiographies : R4 et R5 côte à côte, puis superposition ; activer la zone d'attention ; tableau des scores avec la marge d'incertitude ; choisir « Stabilité » comme jugement | « Pour les radiographies, un modèle de recherche donne des scores avec leur incertitude. La variation du score d'emphysème reste dans la marge : l'application ne conclut rien. C'est le médecin qui juge l'évolution. » |
| 8 | 3:35-4:05 | Tableau de bord, bas de page : Générer la fiche, aperçu, Télécharger le PDF | « Avant la consultation, la fiche résume le dossier sur une page. Chaque chiffre porte un petit numéro qui renvoie au document d'origine. » |
| 9 | 4:05-4:25 | Onglet Assistant : « De combien le VEMS a-t-il varié entre le 20/11/2025 et le 05/11/2026 ? » puis « Quel traitement dois-je prescrire ? » | « On peut aussi interroger le dossier. Les réponses sont lues dans les données validées et citées. Une demande de prescription est refusée. » |
| 10 | 4:25-4:30 | Retour au tableau de bord, logo | « MediMind : l'IA lit et cherche, le code calcule, le médecin décide. » |

**Conseils** : faire une prise par séquence, couper les attentes de lecture au montage ; enregistrer le son à part ; vérifier qu'aucun nom réel n'apparaît (tous les noms sont fictifs).
