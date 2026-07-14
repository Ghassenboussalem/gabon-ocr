# PROMPT — réparer le stack OpenCRVS local (à coller dans une nouvelle session Claude)

Lis d'abord `HANDOFF.md` et `OPENCRVS_LOCAL.md` dans `C:\Users\Ghassen\Documents\gabon-ocr` (contexte complet du projet). Ensuite résous CE problème précis :

## Problème

Stack OpenCRVS de dev (core v1.9.14) dans la distro WSL `ubuntu-opencrvs`, dépôts dans `/opt/opencrvs/{opencrvs-core,opencrvs-countryconfig}`. Chaque service tourne via une tâche planifiée Windows `opencrvs-<service>` qui exécute `wsl -d ubuntu-opencrvs -u root -- bash -c "bash /root/run_<service>.sh > /var/log/opencrvs-<service>.log 2>&1"` (script = `cd packages/<service> && yarn start`).

État actuel : **9 services répondent** (auth:4040, user-mgnt:3030, workflow:5050, search:9090, metrics:1050, notification:2020, config:2021, documents:9050, webhooks:2525 — tous /ping = 200) mais **5 restent à 000 depuis >15 min** : events:5555, gateway:7070, client:3000, login:3020, countryconfig:3040. Leurs logs montrent qu'ils démarrent (gateway fait son gen:schema, client lance vite) mais les ports ne s'ouvrent jamais.

## Pistes à vérifier (dans l'ordre)

1. Lire la FIN des logs : `wsl -d ubuntu-opencrvs -u root -- tail -40 /var/log/opencrvs-gateway.log` (idem events, client, login, countryconfig). Chercher crash, OOM, port déjà pris, boucle nodemon.
2. Processus en double : `wsl -d ubuntu-opencrvs -u root -- pgrep -a -f nodemon` — des watchers orphelins des anciens arbres lerna peuvent tenir les ports ou corrompre `packages/gateway/src/graphql/schema.d.ts` (déjà arrivé : deux watchers gen:types écrivent en même temps → fichier à 0 octet → gateway crash "schema.d.ts is not a module"). Si 0 octet : tuer les orphelins (`pkill -9 -f 'gen:type[s]'` etc.), régénérer `yarn gen:schema && yarn gen:types` dans packages/gateway, relancer la tâche.
3. RAM : `wsl -d ubuntu-opencrvs -u root -- free -m` — 14 services + vite sur 10 Go, si OOM (dmesg) alors démarrage échelonné (attendre que le lot 1 soit vert avant client/login).
4. Tâches en état "Queued" = condition batterie (normalement corrigée via AllowStartIfOnBatteries — vérifier `(Get-ScheduledTask opencrvs-gateway).State`).
5. En dernier recours, redémarrage total propre : arrêter toutes les tâches opencrvs-*, `wsl -d ubuntu-opencrvs -u root -- pkill -9 -f node`, puis relancer les 14 tâches (ou `start-opencrvs.ps1`).

## Pièges connus de cet environnement (ne pas retomber dedans)

- Git Bash mange les chemins POSIX passés à wsl → préfixer `MSYS_NO_PATHCONV=1`.
- `pkill -f` se matche lui-même → écrire le motif avec des crochets : `'motif[x]'`.
- Ne jamais lancer de longs process via `nohup` dans WSL (tués à la fermeture de session) → tâches planifiées uniquement.
- PowerShell appelé DEPUIS bash : les `$variables` PowerShell sont mangées par bash → utiliser l'outil PowerShell directement.
- `.ps1` en ASCII pur (PS 5.1 + UTF-8 sans BOM = erreurs de parse).
- Mongo peut perdre des données sur arrêt brutal (rollback) → si les logins échouent avec "Incorrect username or password" alors que user-mgnt répond : relancer la tâche `opencrvs-seed`, attendre `/tmp/seed.done`, vérifier `db.users.count()` ≈ 12.

## Critères de réussite (dans l'ordre)

1. Les 14 endpoints répondent 200 (liste des ports ci-dessus + les 5 en panne).
2. Connexion à http://localhost:3020 avec `j.campbell` / `test` (2FA `000000`) fonctionne.
3. L'utilisateur recrée le client d'intégration (Configuration → Integrations → Create client, type Event notification) — lui demander le Client ID/Secret et les mettre dans `.env` (`OPENCRVS_CLIENT_ID/SECRET`).
4. Test final : `cd C:\Users\Ghassen\Documents\gabon-ocr && .venv\Scripts\python.exe tools\send_to_opencrvs.py runs\mg_batch_test` → doit imprimer un event id. Le dossier prérempli doit apparaître dans la file Notifications (login `k.mweene`/`test`).
5. Si des correctifs durables sont trouvés, les reporter dans `start-opencrvs.ps1` + `OPENCRVS_LOCAL.md`, commit + push.
