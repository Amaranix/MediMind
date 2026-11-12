# MediMind AI : aide à la décision pour le suivi longitudinal des patients respiratoires adultes

**Projet de fin d'année, 5IIR IA & Data, EMSI Casablanca**
Réalisé par : Ishak Lamzouri et Ismail Amrani. Encadrant : Pr Adil Chergui. Année 2026.

> **Brouillon** rédigé à partir du dépôt (code, `docs/`, résultats d'évaluation). À relire, compléter (passages marqués « À compléter ») et valider par le binôme et l'encadrant. Les chiffres renvoient aux fichiers de `evaluation/results/`.

---

## Résumé

Un pneumologue qui suit un patient atteint de BPCO, de fibrose pulmonaire ou d'une pneumonie doit reconstituer, avant chaque consultation, l'évolution de dizaines de documents hétérogènes : bilans biologiques de laboratoires différents, explorations fonctionnelles respiratoires (EFR), comptes rendus, ordonnances et radiographies thoraciques, souvent scannés ou photographiés. MediMind est un démonstrateur web qui lit ces documents, en extrait les valeurs (avec OCR pour les scans), les fait **valider par le médecin**, puis les présente sur un axe du temps unique : courbes, tendances, alertes sourcées, frise des traitements, comparaison de radiographies avec des scores d'un modèle de recherche, fiche pré-consultation d'une page et assistant de questions cité. Le principe directeur est qu'aucun chiffre n'est produit par un modèle de langage : les valeurs viennent des documents, les calculs du code, et chaque sortie cite sa source. Évalué sur des patients synthétiques jamais utilisés pendant le développement, l'extraction atteint un F1 de 0,974 (1,000 sur PDF natifs, 0,880 sur scans) ; le modèle d'imagerie obtient une AUC externe de 0,773 pour la pneumonie sur 1 500 radiographies RSNA ; l'assistant répond juste et cite toutes ses sources sur les 60 questions de référence. L'expérience de rédaction par un LLM local, mesurée puis retirée de l'application, illustre la nécessité de ce principe.

**Mots-clés** : aide à la décision clinique, extraction d'information, OCR, BPCO, fibrose pulmonaire, radiographie thoracique, TorchXRayVision, LLM local, hallucinations, traçabilité.

---

## 1. Introduction

### 1.1 Contexte

Le suivi d'une maladie respiratoire chronique repose sur l'évolution de quelques paramètres : VEMS et CVF (post-bronchodilatateur), DLCO, saturation, CRP et numération, et l'aspect des radiographies. Au Maroc comme ailleurs, ces données arrivent sur papier ou en PDF de laboratoires différents, avec des unités et des présentations variées (CRP en mg/L ou mg/dL, créatinine en mg/L ou µmol/L). Le médecin reconstitue l'évolution à la main, ce qui prend du temps et expose à des oublis (une baisse progressive du VEMS, une CRP qui ne se normalise pas après antibiotique).

### 1.2 Problématique

Comment aider un pneumologue à visualiser l'évolution d'un patient à partir de documents hétérogènes, **sans** introduire d'erreurs que l'outil inventerait, et en gardant le médecin maître de chaque décision ?

### 1.3 Objectifs

1. Lire des documents PDF, scannés ou photographiés, et en extraire les valeurs, traitements et événements.
2. Faire valider chaque valeur par le médecin avant tout usage.
3. Présenter l'évolution (courbes, tendances, frise) et des alertes fondées sur des recommandations publiées.
4. Comparer des radiographies avec des scores d'un modèle de recherche, présentés comme indicatifs.
5. Produire une fiche pré-consultation d'une page et répondre à des questions sur le dossier, toujours avec des sources.
6. Mesurer chaque composant sur des données jamais utilisées pendant le développement.

### 1.4 Périmètre et statut

Démonstrateur de recherche, **non dispositif médical**, patients adultes uniquement, données publiques ou synthétiques uniquement. Les écarts au cahier des charges, validés par l'encadrant, sont listés dans `docs/DECISIONS.md` (D1 à D11).

---

## 2. État de l'art

*À compléter par le binôme (références à vérifier et à enrichir).* Pistes :

- **Extraction d'information dans les documents médicaux** : OCR (Tesseract), approches par règles et expressions régulières, modèles de compréhension de documents (LayoutLM), LLM pour l'extraction ; la difficulté des scans et des unités.
- **IA en radiographie thoracique** : CheXNet (Rajpurkar et al., 2017), ChestX-ray14 (Wang et al., 2017), CheXpert (Irvin et al., 2019), TorchXRayVision (Cohen et al., 2022) ; limites connues : étiquettes bruitées, raccourcis appris, généralisation entre centres.
- **LLM et hallucinations** : génération de valeurs non présentes dans la source, risques en santé ; stratégies de génération contrainte, vérification et RAG avec citations.
- **Outils existants** : dossiers patients informatisés, tableaux de bord de suivi ; la plupart supposent des données déjà structurées.
- **Cadre marocain** : loi 09-08 (protection des données personnelles, CNDP), loi 84-12 (dispositifs médicaux).

---

## 3. Analyse et conception

### 3.1 Utilisateurs et besoins

Utilisateur principal : le pneumologue adulte ; utilisateur technique : un administrateur qui gère les comptes **sans accès** aux dossiers. Dix-huit histoires d'utilisateur (`docs/user-stories.md`) et quatre diagrammes UML (`docs/uml/` : cas d'usage, deux séquences, classes).

### 3.2 Exigences non négociables

L'IA ne diagnostique jamais ; seules les mesures validées alimentent courbes, alertes et fiches ; aucun nombre généré par un LLM ; LLM local uniquement ; chaque règle d'alerte cite sa source ; chaque sortie d'IA garde la version du modèle et du référentiel ; patients mineurs refusés.

### 3.3 Architecture

Cinq services Docker Compose : proxy HTTPS (Caddy), frontend (React, TypeScript, Tailwind), backend (FastAPI, SQLAlchemy, Alembic), base PostgreSQL 16, et le LLM local Ollama sur l'hôte. Les modèles d'imagerie et de recherche sont intégrés à l'image du backend (fonctionnement hors ligne). Les traitements longs (lecture, OCR, analyse d'image) passent par une table de tâches et des tâches de fond. Détails : `docs/architecture.md`.

### 3.4 Données

- **Référentiel clinique** (`referential/referentiel_clinique.yaml`, v0.2.0) : 20 paramètres avec synonymes, unités et conversions, plages de référence, variation cliniquement significative, sens d'amélioration ; 8 règles d'alerte sourcées (GOLD 2025, ERS/ATS 2022, critères de progression de fibrose ATS/ERS/JRS/ALAT 2022...).
- **Dossiers synthétiques** : 36 patients (12 BPCO, 12 pneumonies, 12 fibroses), 846 documents (PDF natifs, scans dégradés, photos, radiographies) produits par un générateur maison avec vérité terrain ; 4 gabarits de laboratoire, dont un réservé aux 6 patients de test (D9).
- **Radiographies publiques** : NIH ChestX-ray14 (60 patients, séries) et RSNA Pneumonia (1 500 images, évaluation).

---

## 4. Réalisation

*Captures d'écran : voir `docs/captures/` (à insérer).*

### 4.1 Module A : ingestion et validation

Dépôt multiple ; type réel détecté par signature binaire ; empreinte SHA-256 (doublons) ; texte des PDF natifs (PyMuPDF), OCR des scans et photos (redressement, filtre médian, seuil d'Otsu, Tesseract français) ; classification par règles pondérées ; extraction par mise en page (4 gabarits de bilan, EFR à colonnes, comptes rendus) ; normalisation (synonymes, unités, contexte pré/post-bronchodilatateur, plausibilité, dédoublonnage). Écran de validation : document avec les zones lues surlignées, valider / corriger / rejeter au clavier, validation groupée réservée aux valeurs sûres. Le LLM local n'intervient qu'en repli, et une valeur proposée par lui doit figurer mot pour mot dans le texte.

### 4.2 Modules B et D : évolution, traitements, alertes

Séries des seules valeurs validées ; courbes en SVG sur un axe du temps partagé avec la frise des traitements (barres au long cours ou courtes) et des événements (exacerbations, hospitalisations) ; tendances par l'estimateur de Theil-Sen qualifiées par le seuil cliniquement significatif du référentiel ; quatre types de règles d'alerte (seuil, hausse, variation sur fenêtre, contrôle après traitement), chacune citant sa source et ses valeurs, réservées à une pathologie si besoin ; tableau dernière / précédente / variation ; comparaison de deux périodes ; export PNG et PDF.

### 4.3 Module C : imagerie

Analyse au dépôt (TorchXRayVision, 10 pathologies), incertitude par 7 variantes de l'image, contrôles de qualité, carte d'attention Grad-CAM avec légende obligatoire ; visionneuse côte à côte ou en superposition, zoom synchronisé ; scores ± incertitude sur l'axe du temps ; jugement de l'évolution saisi **par le médecin** ; annotations (flèches, textes) ; recalage et carte de différence avec indicateur de qualité d'alignement.

### 4.4 Module E : fiche et assistant

**Dossier de faits** calculé par le code (dernières valeurs, variations, tendances, alertes, traitements, radiographies comparées), chaque fait renvoyant à sa mesure ou à son document. **Fiche** d'une page A4 par gabarit (HTML puis PDF), sources numérotées. **Assistant** : les questions de valeurs, variations, événements, traitements et normalisation sont résolues par des requêtes en base et mises en forme par le code ; les autres questions affichent les passages des documents validés retrouvés par un modèle de recherche multilingue ; refus des demandes de diagnostic ou de prescription.

### 4.5 Sécurité et qualité

HTTPS, en-têtes de sécurité et politique de contenu stricte ; sessions par jeton court et cookie protégé ; limitation des tentatives de connexion ; isolation stricte des dossiers par médecin ; suppression d'un patient en cascade ; journal d'audit ; absence de secrets dans l'historique (gitleaks). 146 tests automatisés (couverture des services 91 %), test de bout en bout du scénario de démonstration dans un navigateur, intégration continue. Checklist : `docs/security-checklist.md`.

---

## 5. Évaluation

Protocole et résultats détaillés : `docs/evaluation-report.md`. Règle : aucun réglage sur les 6 patients de test (`synthetic/splits.json`), évalués une seule fois à la fin.

*Reprendre ici le tableau « cibles et résultats » du rapport d'évaluation, puis discuter :*

- **Extraction** : perfection sur les PDF natifs, baisse sur les scans (0,936 en développement, 0,880 en test), causée par l'OCR de chiffres isolés ; le gabarit tenu à l'écart reste à 0,957, signe d'une généralisation correcte des règles.
- **Imagerie** : l'écart entre la mesure interne (0,827) et externe (0,773) pour la pneumonie illustre la fuite de données des poids publics ; la cible externe ≥ 0,75 est atteinte.
- **Fiche et LLM** : l'ablation montre pourquoi les chiffres ne doivent jamais venir du LLM : à partir des documents bruts, 21 % seulement des nombres écrits sont justifiables ; à partir des faits calculés, 100 %, mais aucune synthèse n'est acceptée à cause des formulations.
- **Extraction : règles ou LLM ?** Sur 15 documents de test, règles seules et hybride F1 0,978 en 0,2 s ; LLM seul F1 0,082 en 62 s (mauvais type de document, listes vides) : le LLM reste un repli.
- **Assistant** : réponses justes et citations complètes sur les 60 questions, mais mesurées sur des données validées ; l'erreur résiduelle d'un système réel viendrait de l'extraction, d'où la validation obligatoire.
- **Utilité** : *À compléter après le test (protocole `docs/usability-protocol.md`).*

---

## 6. Éthique, sécurité et réglementation

- **Statut** : démonstrateur non dispositif médical ; mention permanente « Aide à la décision, pas un diagnostic ». Un produit réel relèverait probablement de la loi 84-12 sur les dispositifs médicaux (dossier technique, gestion des risques ISO 14971, cycle de vie IEC 62304, aptitude à l'utilisation IEC 62366).
- **Données** : uniquement synthétiques ou publiques ; un usage réel imposerait la loi 09-08 (données sensibles, autorisation de la CNDP, consentement, droits d'accès et de rectification, transfert hors du Maroc soumis à autorisation), d'où le choix d'un LLM et d'un hébergement locaux (D3).
- **Garde-fous** : validation humaine obligatoire, aucun chiffre généré, sources partout, refus du diagnostic et de la prescription, traçabilité des versions de modèles et du référentiel, journal d'audit.
- **Équité** : performances de l'imagerie rapportées par sexe et par âge ; données d'entraînement non marocaines.

---

## 7. Limites et perspectives

**Limites** : données synthétiques (générateur et règles conçus par la même équipe, évaluation en partie circulaire malgré le gabarit tenu à l'écart) ; aucun clinicien dans la boucle d'évaluation ; modèle d'imagerie non recalibré et non validé sur une population marocaine ; LLM local trop peu fiable pour rédiger ; recalage rigide des radiographies ; test d'utilité restreint et non clinique.

**Perspectives** : étude sur documents réels anonymisés avec autorisation de la CNDP ; validation par des pneumologues ; recalibrage et évaluation de l'imagerie sur données locales ; modèles de compréhension de documents pour les scans ; intégration à un dossier patient (HL7 FHIR) ; démarche de certification ; étude de marché au Maroc (PLAN §12).

---

## 8. Conclusion

*À compléter par le binôme.* Idée directrice : MediMind montre qu'on peut rendre l'IA utile au suivi longitudinal sans lui confier ce qu'elle fait mal, en lui faisant lire et chercher, en laissant le calcul au code et la décision au médecin.

---

## Annexes

- A. Référentiel clinique : `referential/referentiel_clinique.yaml`.
- B. Fiche des modèles : `docs/model-card.md`.
- C. Décisions et écarts au cahier des charges : `docs/DECISIONS.md`.
- D. Protocole du test d'utilité : `docs/usability-protocol.md`.
- E. Checklist sécurité : `docs/security-checklist.md`.
