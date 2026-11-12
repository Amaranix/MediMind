# Checklist sécurité (étape 8.1)

> Démonstrateur de recherche, données fictives uniquement. Vérifiée le 12/11/2026. Chaque ligne indique comment elle a été contrôlée.

## Transport et navigateur

- [x] **HTTPS partout** : Caddy (`tls internal`) sur le port 8443 ; le backend et la base ne sont pas exposés sur l'hôte. *Contrôle : `docker compose ps`, seuls 8443 est publié.*
- [x] **En-têtes de sécurité** : `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy`, en-tête `Server` retiré. *Contrôle : `curl -skI https://localhost:8443/`.*
- [x] **Content-Security-Policy stricte** : scripts du seul site (aucun script en ligne ni externe), images `self`/`blob:`/`data:`, `object-src 'none'`, `frame-ancestors 'none'`. *Contrôle : parcours complet dans Chromium (fiche, export PNG, radiographies et carte d'attention, carte de différence, validation, assistant), zéro violation CSP.*
- [x] **CORS strict** : aucune origine tierce autorisée (pas de middleware CORS) ; le frontend et l'API partagent la même origine via Caddy.

## Authentification et sessions

- [x] **Mots de passe** hachés avec bcrypt ; 10 caractères minimum à la création d'un compte.
- [x] **Jetons** : accès 15 min en mémoire du navigateur ; rafraîchissement 7 j en cookie `httpOnly`, `Secure`, `SameSite=Strict`, limité à `/api/auth` (T11).
- [x] **Limitation des tentatives** : 5 échecs en 15 min par compte ou par adresse IP => 429 avec `Retry-After`, même avec le bon mot de passe ; blocages audités. *Contrôle : `test_login_attempts_are_limited`.* Limite connue : compteur en mémoire d'un seul processus (commentaire `shortcut:` dans `app/core/ratelimit.py`).
- [x] **Rôles et isolation** : un médecin ne voit que ses patients (toute route patient passe par `get_patient_for_doctor`) ; l'administrateur gère les comptes sans accès aux dossiers. *Contrôle : `test_isolation.py` et les tests « autre médecin => 404 » de chaque module (documents, alertes, fiches, radiographies, comparaisons, carte de différence, assistant, suppression).*

## Fichiers déposés

- [x] **Type réel** déterminé par la signature binaire (PDF, PNG, JPEG), jamais par le nom ni l'en-tête du navigateur. *Contrôle : `test_duplicate_and_unsupported_files`.*
- [x] **Taille maximale** : 25 Mo par fichier côté API, 30 Mo par requête côté Caddy.
- [x] **Noms de fichiers générés côté serveur** (`<patient>/<uuid>.<ext>`) ; chemins vérifiés à l'intérieur du volume de stockage (`storage.absolute`).
- [x] **Aperçus isolés** : la fiche HTML est affichée dans une `iframe sandbox` sans script ; le gabarit Jinja2 échappe tout le contenu.

## Données et traçabilité

- [x] **Suppression d'un patient** : base en cascade (documents, mesures, traitements, événements, alertes, imagerie, comparaisons, fiches, conversations, passages indexés de l'assistant), dossier de fichiers du patient, tâches liées ; confirmation par saisie du nom ; action auditée. *Contrôle : `test_patient_deletion_cascades_to_data_and_files`.*
- [x] **Journal d'audit** : connexions (réussies, échouées, bloquées), lectures et modifications de dossier, décisions de validation, générations de fiche, questions à l'assistant, suppressions.
- [x] **Aucun appel externe avec des données patient** : LLM local (Ollama sur l'hôte) ; modèles d'imagerie et de recherche intégrés à l'image Docker, `HF_HUB_OFFLINE=1`.
- [x] **Patients mineurs refusés** à la saisie.

## Secrets

- [x] **`.env` jamais versionné** (`.gitignore`) ; `.env.example` ne contient que des valeurs « a-changer ».
- [x] **Historique Git sans secret** : `gitleaks git` sur les 23 commits ; 2 faux positifs (mot de passe factice d'un test) consignés dans `.gitleaksignore`, puis « no leaks found ». Le jeton Kaggle n'apparaît dans aucun commit. *Commande : `docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:v8.21.2 git /repo`.*
- [x] **Jeton Kaggle** révoqué après les téléchargements (il avait été affiché en clair dans une conversation).

## Limites assumées (démonstrateur)

- Compte de démonstration à mot de passe connu (`berrada@medimind.local`), créé par `scripts/seed_demo.py` : à ne jamais créer sur une instance contenant de vraies données.
- Certificat auto-signé (autorité locale de Caddy) ; un déploiement réel demanderait un certificat d'une autorité reconnue.
- Pas de chiffrement applicatif de la base ni des fichiers au repos ; hors périmètre du PFA (données fictives), indispensable en cas d'usage réel (loi 09-08, PLAN §12).
