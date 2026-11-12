# Fiche des modèles d'IA de MediMind (model card)

> **Démonstrateur de recherche, non dispositif médical.** Aucun des modèles ci-dessous ne pose de diagnostic. Toute sortie est présentée comme une aide à la décision et reste soumise à la lecture du médecin. Ne pas utiliser pour une décision clinique.

MediMind combine trois modèles pré-entraînés, aucun n'a été ré-entraîné ni affiné (décision D11).

| Rôle | Modèle | Où il intervient |
|---|---|---|
| Scores de pathologies sur radiographie thoracique | TorchXRayVision `densenet121-res224-all` (v1.5.7) | Onglet Radiographies, courbe des scores IA, fiche |
| Recherche de passages dans les documents | `intfloat/multilingual-e5-small` | Assistant, questions libres (passages affichés tels quels) |
| Repli de lecture des documents | `llama3.2:3b` (Ollama, local) | Classification et extraction quand les règles ne reconnaissent rien ; rédaction de la fiche **retirée** (T35) |

---

## 1. Modèle d'imagerie

### Description

- **Architecture** : DenseNet-121, entrée 224 × 224 en niveaux de gris, 18 sorties (MLP multi-étiquettes) ; 10 sont affichées (consolidation, pneumonie, opacité, infiltrat, épanchement, atélectasie, emphysème, fibrose, œdème, cardiomégalie).
- **Poids** : `densenet121-res224-all` de TorchXRayVision (Cohen et al., 2022), entraînés sur la réunion de 7 jeux publics (NIH ChestX-ray14, PadChest, CheXpert, MIMIC-CXR, Google, OpenI, RSNA Pneumonia « kaggle »). Intégrés à l'image Docker, inférence sur CPU.
- **Sorties ajoutées par MediMind** : incertitude (écart-type sur 7 variantes de l'image : rotation ± 4°, décalage, contraste) ; carte d'attention Grad-CAM par pathologie ; contrôles de qualité (couleur, résolution < 512 px, proportions, contraste) ; variation entre deux clichés jugée « dans la marge » si |Δ| ≤ 2·√(σ₁²+σ₂²) + 0,02 (T29).
- **Durée** : 1,9 s par radiographie dans Docker (analyse + incertitude) ; 3,2 s du dépôt à l'affichage.

### Usage prévu

Suivre l'**évolution relative** d'un score entre deux radiographies du même patient adulte, en complément de la lecture du médecin. Le médecin qualifie lui-même l'évolution (amélioration, stabilité, aggravation, non évaluable) ; l'application ne produit aucun verdict d'évolution (D5).

### Usages interdits

Dépistage ou diagnostic ; tri de patients ; patients de moins de 18 ans (refusés à la saisie) ; vues de profil (exclues des comparaisons) ; images autres que des radiographies thoraciques de face ; toute décision sans lecture humaine.

### Évaluation (RSNA Pneumonia, 1 500 adultes, 500 positifs « Lung Opacity »)

Deux mesures, pour rendre visible la fuite de données (T30) : les poids `-all` ont vu RSNA à l'entraînement (mesure **interne, optimiste**) ; les poids `-chex` (CheXpert seul) ne l'ont jamais vu (mesure **externe**). AUC de Mann-Whitney, intervalle de confiance à 95 % par bootstrap.

| Cible RSNA | Externe `-chex` | Interne `-all` |
|---|---|---|
| Opacité pulmonaire | 0,794 [0,773 ; 0,817] | 0,877 [0,859 ; 0,894] |
| **Pneumonie** | **0,773 [0,750 ; 0,797]** (cible ≥ 0,75 atteinte) | 0,827 [0,806 ; 0,849] |
| Consolidation | 0,792 [0,770 ; 0,815] | 0,854 [0,835 ; 0,874] |

**Sous-groupes** (score « Pneumonia », externe) : femmes 0,782 [0,747 ; 0,817], hommes 0,767 [0,738 ; 0,799] ; 18-40 ans 0,803 [0,765 ; 0,843], 41-60 ans 0,761 [0,721 ; 0,795], plus de 60 ans 0,763 [0,709 ; 0,807]. Écart femmes / hommes ≤ 0,02 ; les 18-40 ans sont un peu mieux classés (+0,03 à +0,04), les intervalles se recouvrent.

**Au seuil de fonctionnement 0,50** (interne) : « Lung Opacity » est très sensible et peu spécifique (Se 0,96, Sp 0,55) ; « Pneumonia » l'inverse (Se 0,59, Sp 0,87). Le seuil n'est pas recalibré : l'application montre le score, pas une décision.

### Biais et limites connus

- **Fuite de données** : l'AUC interne surestime la performance (environ +0,05 à +0,08) ; c'est l'AUC externe qui doit être citée.
- **Étiquettes bruitées** : NIH ChestX-ray14 (séries de démonstration) a des étiquettes extraites automatiquement des comptes rendus.
- **Scores regroupés autour de 0,50** pour plusieurs pathologies (calibration du modèle) : une petite variation n'a pas de sens clinique, d'où la marge d'incertitude.
- **Raccourcis appris** : la carte Grad-CAM porte parfois sur les bords de l'image, le cou ou les marqueurs ; légende obligatoire « zone d'attention, pas une localisation de lésion ».
- **Population** : jeux nord-américains et européens ; aucune donnée marocaine ; pas d'évaluation par appareil ou par centre.
- **Pas d'évaluation de l'évolution** : aucune vérité terrain d'évolution entre deux clichés n'existe dans les données (D5).
- **Carte de différence (F-C8)** : recalage rigide ; sur des clichés d'inspiration ou de cadrage différents, la carte reflète surtout le positionnement (A01, R4/R5 : corrélation 0,61 → 0,65, signalée « alignement insuffisant »).

---

## 2. Modèle de recherche de l'assistant

- **Modèle** : `intfloat/multilingual-e5-small` (384 dimensions), CPU, intégré à l'image (`HF_HUB_OFFLINE=1`).
- **Usage** : retrouver, dans le texte des **documents validés**, les passages les plus proches d'une question libre ; les passages sont affichés **tels quels**, avec le document et la date. Aucune phrase n'est générée.
- **Réglage** : en-têtes répétés et radiographies exclus de l'index ; seuil de similarité 0,83 mesuré sur A01 (passages pertinents 0,84 à 0,88, questions hors sujet ≤ 0,82). **Marge étroite** : une question hors sujet peut parfois afficher des passages, d'où l'affichage du score de proximité.
- **Questions de valeurs, dates, traitements, événements** : elles ne passent pas par ce modèle mais par des requêtes en base (T36).

---

## 3. LLM local (`llama3.2:3b`)

- **Usage conservé** : repli quand les règles ne reconnaissent pas le type d'un document ou n'extraient aucune valeur d'un compte rendu ; une valeur proposée par le LLM n'est gardée que si elle figure mot pour mot dans le texte ; le nom du modèle est noté sur le document ; le médecin valide chaque valeur.
- **Usage retiré** : rédaction de la synthèse de la fiche (T35). Mesures : 1 synthèse acceptée sur 12 par le vérificateur ; erreurs relevées : « BPCO depuis 40 ans » (40 paquets-années), « post-BD (biopsie du poumon) », « souffre de », tendances contraires aux faits, « augmentation » d'un score resté dans la marge ; 37 à 129 s par fiche.
- **Confidentialité** : exécuté sur l'hôte, aucun appel réseau externe avec des données patient (D3).

---

## Références

- Cohen JP, et al. TorchXRayVision: A library of chest X-ray datasets and models. MIDL 2022.
- Wang X, et al. ChestX-ray8. IEEE CVPR 2017. Shih G, et al. RSNA Pneumonia. Radiology: Artificial Intelligence 2019.
- Wang L, et al. Multilingual E5 Text Embeddings. arXiv 2402.05672, 2024.
- Mitchell M, et al. Model Cards for Model Reporting. FAT* 2019.
