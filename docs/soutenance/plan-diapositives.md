# Plan des diapositives de soutenance (étape 10.5)

**Durée** : 20 min de présentation (dont 5 min de démonstration) + questions. **15 diapositives.** Une idée par diapositive ; texte court, le reste se dit à l'oral.

| # | Titre | Contenu | Visuel | Orateur |
|---|---|---|---|---|
| 1 | MediMind AI | Aide à la décision pour le suivi des patients respiratoires adultes ; binôme, encadrant, EMSI 5IIR IA & Data, 2026 | Logo, capture du tableau de bord | Ismail |
| 2 | Le problème | Un dossier = des dizaines de documents hétérogènes (labos, unités, scans) ; l'évolution se reconstitue à la main ; risque d'oubli (VEMS qui baisse, CRP qui ne se normalise pas) | Pile de documents réels-type (fictifs) | Ismail |
| 3 | L'utilisateur | Le pneumologue, avant la consultation ; ce qu'il veut voir en 2 minutes | Persona + 3 besoins | Ishak |
| 4 | Notre réponse | Lire → faire valider → aligner sur un axe du temps → alerter avec sources → résumer | Schéma en 5 étapes | Ishak |
| 5 | Principe directeur | « L'IA lit et cherche, le code calcule, le médecin décide » ; aucun chiffre généré par un LLM ; sources partout | Trois colonnes | Ismail |
| 6 | Architecture | Caddy, React, FastAPI, PostgreSQL, modèles intégrés, LLM local ; tout tourne en local (loi 09-08) | Schéma d'architecture | Ishak |
| 7 | Les données | Référentiel sourcé (20 paramètres, 8 règles) ; 36 patients synthétiques, 846 documents ; NIH et RSNA ; 6 patients et 1 gabarit tenus à l'écart | Chiffres clés | Ishak |
| 8 | Démonstration | Démo en direct (scénario A01) ; vidéo de secours | Bascule vers l'application | Les deux |
| 9 | Résultats : extraction | F1 0,974 en test ; natif 1,000 ; scans 0,880 ; gabarit jamais vu 0,957 ; type et date 100 % | Tableau cibles / résultats | Ismail |
| 10 | Résultats : imagerie | AUC pneumonie 0,773 externe (cible 0,75) contre 0,827 interne : la fuite de données rendue visible ; sous-groupes | Graphique des AUC avec intervalles | Ishak |
| 11 | Pourquoi pas un LLM pour rédiger ? | Ablation : 21 % de nombres justifiables à partir des documents bruts ; 100 % à partir des faits mais formulations fausses ; exemples réels | Tableau + 2 exemples d'erreurs | Ismail |
| 12 | Assistant cité | 60/60 questions justes et sourcées (sur données validées) ; refus du diagnostic | Capture de l'assistant | Ishak |
| 13 | Garde-fous et sécurité | Validation obligatoire, bandeau, audit, isolation, CSP, suppression en cascade ; non dispositif médical | Icônes + checklist | Ismail |
| 14 | Limites et perspectives | Données synthétiques, pas de clinicien, imagerie non validée au Maroc ; perspectives : données réelles avec la CNDP, validation clinique, FHIR, certification | Deux colonnes | Ishak |
| 15 | Conclusion | Ce que MediMind démontre ; merci ; questions | Capture finale | Les deux |

**Diapositives de réserve (après la 15)** : détail des règles d'alerte et de leurs sources ; résultats imagerie par âge et sexe ; ablation de l'extraction ; protocole et résultats du test d'utilité ; modèle de données.

**Répétitions** : deux soutenances à blanc chronométrées (roadmap 10.5), dont une devant l'encadrant ; préparer les réponses de `questions-jury.md`.
