# Questions probables du jury et éléments de réponse (étape 10.5)

> À s'approprier et reformuler avec vos mots. Chaque réponse renvoie à une preuve du dépôt.

## Données et évaluation

**Pourquoi des données synthétiques ?**
Utiliser de vrais dossiers médicaux exige, au Maroc, une autorisation de la CNDP (loi 09-08) et un cadre de recherche que le PFA n'a pas. Le générateur produit 36 patients avec leur vérité terrain, ce qui permet de mesurer précisément l'extraction. Limite assumée : les règles et le générateur viennent de la même équipe ; pour la réduire, un gabarit de laboratoire et 6 patients ont été tenus à l'écart jusqu'à l'évaluation finale (D9). Preuve : `synthetic/splits.json`, `evaluation/results/extraction_test.json`.

**Vos résultats ne sont-ils pas trop beaux ?**
Sur les PDF natifs, le texte est exact, donc 1,000 est attendu. La difficulté réelle est l'OCR : 0,880 sur les scans en test, en baisse par rapport au développement (0,936), et nous le rapportons. Pour l'assistant, 100 % est mesuré sur des données déjà validées : c'est la logique de réponse qui est évaluée, pas l'extraction.

**Qu'est-ce que la fuite de données en imagerie ?**
Les poids publics `-all` ont été entraînés notamment sur RSNA : les évaluer sur RSNA est optimiste (AUC pneumonie 0,827). Nous avons aussi mesuré les poids `-chex`, qui n'ont jamais vu RSNA : 0,773, c'est le chiffre à retenir (T30, `docs/model-card.md`).

**Le modèle est-il biaisé ?**
AUC par sexe : écart ≤ 0,02. Par âge : les 18-40 ans un peu mieux classés, intervalles qui se recouvrent. Données d'entraînement nord-américaines et européennes, aucune donnée marocaine : c'est une limite.

## IA générative et hallucinations

**Pourquoi ne pas laisser un LLM rédiger la fiche ?**
Nous l'avons mesuré (étape 6.3 et ablation 9.4). LLM sur les documents bruts : 21 % seulement des nombres justifiables. LLM sur nos faits calculés : 100 % des nombres justes, mais des formulations fausses (« BPCO depuis 40 ans » pour 40 paquets-années, « post-BD (biopsie du poumon) », tendances contraires). Le vérificateur a bloqué toutes ces erreurs ; nous avons retiré l'option de l'application (T35).

**Alors où est l'IA dans votre projet ?**
OCR, détection des documents et de leurs valeurs, modèle de radiographie (scores, incertitude, carte d'attention), recherche sémantique multilingue dans les documents, et le LLM local en repli de lecture. Ce que nous refusons à l'IA : inventer des chiffres et décider.

**Votre assistant est-il un RAG ?**
Oui pour la partie recherche (passages retrouvés par plongements e5, affichés tels quels avec leur source), mais sans génération : les questions de valeurs passent par des requêtes en base. C'est un choix de sûreté, pas une limite technique (T36).

## Clinique et réglementation

**Un médecin a-t-il validé l'outil ?**
Non, et c'est la limite principale. Le référentiel cite des recommandations publiées (GOLD 2025, ERS/ATS 2022, ATS/ERS/JRS/ALAT 2022) et a été validé par l'encadrant ; le test d'utilité est un test proxy, non clinique.

**Est-ce un dispositif médical ?**
Ce démonstrateur ne l'est pas : données fictives, mention permanente « aide à la décision ». Un produit qui affiche des scores de pathologie en relèverait probablement (loi 84-12), avec gestion des risques (ISO 14971) et cycle de vie logiciel (IEC 62304).

**Et la confidentialité ?**
Tout tourne sur la machine : LLM local, modèles intégrés à l'image, aucun appel externe avec des données patient (D3). Isolation des dossiers par médecin, journal d'audit, HTTPS, suppression en cascade (`docs/security-checklist.md`).

## Choix techniques

**Pourquoi pas de GPU, pas d'affinage du modèle ?**
La machine cible n'a pas de GPU et le modèle pré-entraîné suffit pour un démonstrateur (D11). Inférence : 1,9 s par radiographie sur CPU.

**Pourquoi des règles et pas un modèle pour l'extraction ?**
Elles sont exactes, explicables et rapides (0,7 s par document) sur des gabarits connus ; le LLM reste un repli. L'ablation 9.5 compare règles seules, LLM seul et hybride (`evaluation/results/extraction_ablation.json`).

**Comment garantissez-vous qu'une alerte est juste ?**
Chaque règle est un seuil publié, codé et testé sur 24 cas de référence (100 %) ; elle ne porte que sur des données validées et cite ses valeurs et sa source.

**Qu'avez-vous appris des tests ?**
Le test sur une machine propre a révélé quatre défauts réels (port configurable inopérant, blocage du serveur sous charge, données non rafraîchies, chemins de fichiers Windows), corrigés avant la livraison.
