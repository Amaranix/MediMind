# Système visuel MediMind

Maquettes : ouvrir `index.html` dans un navigateur (navigation en bas à droite). Données fictives. Ces choix sont à reprendre tels quels dans `frontend/` (variables CSS → thème Tailwind).

## Idée directrice

**Un seul axe du temps.** Courbes, frise des traitements et radiographies partagent la même échelle temporelle ; un curseur unique les traverse et chaque paramètre affiche sa valeur à la date survolée. C'est l'élément distinctif de l'interface ; le reste reste sobre.

## Couleurs

| Jeton | Valeur | Usage |
|---|---|---|
| `--paper` | #F6F8F7 | Fond de l'application (référence au papier de spirométrie) |
| `--surface` | #FFFFFF | Panneaux, tableaux |
| `--ink` | #1D2A31 | Texte, courbes validées |
| `--grid` | #DCE6E3 | Quadrillage, séparateurs |
| `--teal` | #0E6B6B | Actions principales, sélection, seuils |
| `--alert` | #A8233F | Alertes, valeurs hors zone, exacerbations |
| `--warn` | #9A6400 | À valider, confiance faible |
| `--ok` | #2C6E45 | Validé, amélioration |
| `--info` | #3B5B8C | Alertes informatives, scores IA |
| `--lightbox` | #14181B | Visionneuse de radiographies uniquement |

## Typographie

Atkinson Hyperlegible Next (Google Fonts), une seule famille, chiffres tabulaires. Conçue pour la lisibilité (0 barré, 1/l/I distincts), important pour des valeurs cliniques.

## Règles d'interface

- Bandeau « Aide à la décision » permanent en haut de l'écran.
- Valeur non validée : cercle en pointillé, jamais reliée à la courbe ni utilisée dans les calculs.
- Valeur hors zone : cercle blanc à contour rouge ; zone de référence en aplat vert pâle.
- Chaque alerte affiche règle, source bibliographique et valeurs déclenchantes, avec bouton « Acquitter ».
- Grad-CAM toujours légendé « zone d'attention du modèle, pas une localisation de lésion ».
- Scores IA toujours avec ± incertitude et nom/version du modèle.
- Fiche : chaque nombre porte un numéro de source ; un panneau « Contrôle » affiche le résultat du vérificateur.
- Pas de libellés en majuscules, pas de cartes ombrées identiques, pas de flèches dans les boutons.
