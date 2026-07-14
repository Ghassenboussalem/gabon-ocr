# HANDOFF — état complet du projet (pour une nouvelle session Claude)

> Contexte : OCR d'actes d'état civil africains + intégration OpenCRVS.
> Machine : Windows 11, 14 Go RAM, projet dans `C:\Users\Ghassen\Documents\gabon-ocr`.
> Une mémoire persistante existe aussi dans `~\.claude\projects\C--Users-Ghassen-Documents-gabon-ocr\memory\`.

---

## 1. Les deux dépôts

| Dépôt | Rôle |
|---|---|
| `Ghassenboussalem/gabon-ocr` (ce dossier) | Pipeline OCR + app web + export OpenCRVS |
| `Ghassenboussalem/opencrvs-countryconfig` (branche `main-poc`) | **Fork manuel** du repo privé `EY-DPI/opencrvs-countryconfig` (le fork GitHub était désactivé → clone+push). Règle du superviseur : ne JAMAIS toucher au repo EY-DPI. Cloné aussi dans WSL : `/opt/opencrvs/opencrvs-countryconfig` |

Le token GitHub est dans le gestionnaire d'identifiants Windows (compte réel : Ghassenboussalem).

## 2. Pipeline OCR (fait, fonctionne)

`run_pipeline.py <scan> --backend gemini` : preprocess → localisation → extraction → validation → score → `runs/<doc>/report.json`.

- 27 packs pays (`config/countries/`) + fallback générique. Détection auto du pays.
- Localisation : templates (rapide) + **gate d'honnêteté** (`field_coverage` ≥ 0.6) + fallback **VLM grounding** (`pipeline/vlm_locate.py`) quand le template ne colle pas.
- Extraction (`pipeline/extract.py`) : passe page + passe crops **par lots de 5 images/appel, 4 workers parallèles, thinking bridé** → ~35-50 s/document (avant : ~10 min).
- Clés Gemini : `.env` → `GEMINI_API_KEY` + fallback `_2`/`_3` (rotation auto sur 429). Toutes **free tier** (~250 req/jour flash par clé, buckets séparés par modèle). 403 = problème billing Google ; 429 = quota.
- PDF accepté (première page). Tesseract : fra.traineddata embarqué dans `tessdata/`, résolu automatiquement.

## 3. App web (fait, fonctionne)

`review/app.py` (FastAPI) — lancée par la tâche planifiée `gabonocr-webapp` (port 8000) :
- `/` dépôt : drag-drop (images+PDF), **QR code téléphone** (`/m/<session>`), liste des documents avec statut live.
- `/review` : UI de correction (corrections → `data/corrections.jsonl`).
- Bouton **« → OpenCRVS »** par document → `POST /api/run/<doc>/opencrvs` → notification préremplie ; chip « CRVS ✓ » (event id en tooltip) ; résultat stocké dans `runs/<doc>/opencrvs.json`.
- Déployée aussi sur Render : https://gabon-ocr.onrender.com (repo GitHub, auto-deploy on push, `APP_PASSWORD` en Basic auth, plan free = sommeil après 15 min).

## 4. Intégration OpenCRVS (fait, fonctionne — POC prouvé)

- **Mapping** : `pipeline/opencrvs_export.py` — `build_declaration()` transforme `report.json` en déclaration V2 (`child.name`, `child.dob`, `child.gender`, `mother.*`, `father.*`, `informant.relation`). Noms scindés (MAJUSCULES=nom de famille). **Toute valeur au format valide est préremplie** ; sous le seuil 0.6 elle est en plus signalée « à vérifier » dans le commentaire de revue. Lieux/heures (non structurables) → commentaire seulement. Tests : `tests/test_opencrvs_export.py`.
- **API** (collection Postman `Event Notification - v1.9.0` dans le fork) : token client_credentials (`{auth}/token`) → `POST {gateway}/events/events` → `POST {gateway}/events/events/notifications`. CLI : `tools/send_to_opencrvs.py runs/<doc> [--dry-run]`.
- Config dans `.env` : `OPENCRVS_AUTH_URL=http://localhost:4040`, `OPENCRVS_GATEWAY_URL=http://localhost:7070`, `OPENCRVS_CLIENT_ID/SECRET`, `OPENCRVS_LOCATION_ID` (bureau Ibombo `a89f28b6-7040-4893-9631-162071af6c1a`).
- **Preuve** : plusieurs documents réels envoyés, visibles préremplis dans la file Notifications (ex. tracking `JGQ7O3`). Flux complet upload→registre : **46 s** mesurés.

## 5. Stack OpenCRVS local (fait — voir `OPENCRVS_LOCAL.md` pour l'exploitation)

- WSL distro `ubuntu-opencrvs` (Ubuntu 24.04, D:\wsl), dépôts dans `/opt/opencrvs/` : core **v1.9.14** (même version que l'instance du superviseur) + le fork. Docker Desktop sur D:\Docker. `.wslconfig` = 10 Go.
- **Démarrage = UNE commande** : `powershell -ExecutionPolicy Bypass -File C:\Users\Ghassen\Documents\gabon-ocr\start-opencrvs.ps1` — démarre tout, tableau de bord live, auto-réparation, finit par « TOUT EST VERT ».
- Tâches planifiées Windows (toutes avec `AllowStartIfOnBatteries`) : `opencrvs-services` (arbre lerna), et tâches DÉDIÉES pour les fragiles : `opencrvs-gateway`, `opencrvs-client`, `opencrvs-events`, `opencrvs-login`, `opencrvs-countryconfig`, `opencrvs-seed` (one-shot), `gabonocr-webapp`. Scripts dans `/root/run_*.sh` (distro), logs dans `/var/log/opencrvs-*.log`.
- Ports : auth 4040, gateway 7070, events 5555, user-mgnt 3030, workflow 5050, client 3000, login 3020, countryconfig 3040, app OCR 8000.
- Connexion : http://localhost:3020 — `k.mweene`/`test` (registrar), `j.campbell`/`test` (admin système → menu Configuration), `j.musonda`/`test`. 2FA : `000000`.
- L'UI des captures d'écran du superviseur = **V2 events** (`src/form/v2/birth/forms/pages/*.ts` dans le fork), PAS le legacy `src/form/birth/index.ts`.

## 6. ⚠️ PIÈGES connus (durement appris — lire avant d'agir)

1. **Git Bash + wsl** : préfixer `MSYS_NO_PATHCONV=1` sinon `/var/...` devient `C:/Program Files/Git/var/...`.
2. **WSL tue les processus nohup** quand la session se ferme → toujours passer par les tâches planifiées.
3. Tâches planifiées bloquées en **« Queued »** = condition batterie (corrigée partout via `AllowStartIfOnBatteries`).
4. **JAMAIS `pkill -f node`** dans la distro pendant que le stack tourne (tue les services core). Pattern auto-safe pour pkill : `'motif[x]'` (sinon pkill se matche lui-même).
5. Service unique en panne (000/503) : `wsl -d ubuntu-opencrvs -u root -- touch /opt/opencrvs/opencrvs-core/packages/<svc>/src/index.ts` (nodemon) ou restart de sa tâche dédiée.
6. **`schema.d.ts` du gateway tronqué à 0 octet** = des watchers codegen dupliqués (arbres morts) qui écrivent en même temps. Fix : tuer les orphelins `gen:types`/`gen:schema`, `yarn gen:schema && yarn gen:types` dans packages/gateway, relancer la tâche gateway.
7. **Arrêt brutal du PC → rollback Mongo** (perte users/clients d'intégration alors que Postgres garde tout). Toujours `wsl --shutdown` avant d'éteindre. Réparation : tâche `opencrvs-seed` (+ recréer le client d'intégration).
8. PowerShell 5.1 : pas de `&&`, pas de ternaire ; les `.ps1` doivent être **ASCII pur** (UTF-8 sans BOM = parse errors sur les accents).
9. `run_pipeline` : `sys.stdout.reconfigure(errors="replace")` déjà en place (consoles cp1252).
10. Les envois OpenCRVS ne sont PAS idempotents (renvoyer = doublon).

## 7. ⏭️ À FAIRE — première chose dans la nouvelle session

**Le client d'intégration OpenCRVS a été perdu dans le rollback Mongo (§6.7).** L'utilisateur doit :
1. http://localhost:3020 → `j.campbell`/`test` → Configuration → Integrations → Create client (type **Event notification**)
2. Donner le nouveau Client ID + Secret → les mettre dans `.env` (`OPENCRVS_CLIENT_ID/SECRET`)
3. Vérifier : `.venv\Scripts\python.exe tools\send_to_opencrvs.py runs\mg_batch_test` → event id = OK.

## 8. Feuille de route restante

- **Phase A (en cours)** : ✅ bouton web ; ✅ préremplissage low-confidence ; ⬜ **attacher le scan original** à la déclaration (spike : FILE via l'API notifications / MinIO) ; ⬜ afficher le **tracking ID** (ex. JGQ7O3) au lieu de l'UUID dans le chip + lien direct vers le dossier OpenCRVS.
- **Phase B** : batch des ~25 échantillons + tableau « % champs préremplis » (métrique pour la superviseure) ; idempotence (transactionId = hash du fichier) ; case « envoi auto après traitement ».
- **Phase C** : démo à la superviseure (message WhatsApp déjà rédigé dans la session précédente) puis **migration** : elle crée un client Event notification sur SON instance → changer les 4 URLs/identifiants `OPENCRVS_*` dans `.env` (URLs Tailscale) → zéro changement de code.
- **Phase D (après accord)** : page « upload dans le formulaire » du fork (FieldTypes `FILE`+`HTTP` du toolkit V2, calquer sur le pattern MOSIP `idReaderFields` déjà présent dans `src/form/v2/birth/.../informant.ts`).
- **À dire dans le rapport final** : données d'état civil transitent par l'API Google (prod → VLM local, le pipeline supporte déjà `--backend ollama/openai`) ; quotas free tier ; Render éphémère ; `corrections.jsonl` = futur jeu de fine-tuning.

## 9. Vérifier l'état en 10 secondes

```powershell
# tout démarrer / vérifier :
powershell -ExecutionPolicy Bypass -File C:\Users\Ghassen\Documents\gabon-ocr\start-opencrvs.ps1
# tester le flux complet :
#   http://localhost:8000 → déposer un scan → bouton "→ OpenCRVS"
#   http://localhost:3020 (k.mweene/test) → Notifications → dossier prérempli
```
