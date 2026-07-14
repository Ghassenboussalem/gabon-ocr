# OpenCRVS local — redémarrage après boot du PC

Tout est installé sur **D:** (distro WSL `ubuntu-opencrvs`, dépôts dans
`/opt/opencrvs/`, disque Docker dans `D:\Docker`). La base est **déjà seedée**
— ne jamais relancer le seed, il est fait une fois pour toutes.

## Démarrage (≈5 min)

**1. Lancer Docker Desktop** (menu Démarrer) et attendre que la baleine soit verte.

**2. Vérifier / démarrer les 7 conteneurs de dépendances** — PowerShell :

```powershell
docker ps --format "{{.Names}}: {{.Status}}"
```

S'il manque des conteneurs (hearth, mongo1, elasticsearch, postgres, minio,
redis, influxdb), les relancer :

```powershell
wsl -d ubuntu-opencrvs -u root -- bash -c "cd /opt/opencrvs/opencrvs-core && docker compose -p opencrvs -f docker-compose.deps.yml -f docker-compose.dev-deps.yml up -d"
```

**3. Démarrer les services (tâches planifiées)** — PowerShell :

```powershell
Start-ScheduledTask opencrvs-services        # ~3-4 min de démarrage
Start-ScheduledTask opencrvs-countryconfig   # lancer ~1 min après
Start-ScheduledTask opencrvs-login           # page de connexion :3020
```

**4. Attendre le vert** — tout doit répondre 200 :

```powershell
curl.exe -s -o NUL -w "auth: %{http_code}`n"          http://localhost:4040/ping
curl.exe -s -o NUL -w "gateway: %{http_code}`n"       http://localhost:7070/ping
curl.exe -s -o NUL -w "client: %{http_code}`n"        http://localhost:3000
curl.exe -s -o NUL -w "countryconfig: %{http_code}`n" http://localhost:3040/ping
curl.exe -s -o NUL -w "login: %{http_code}`n"         http://localhost:3020
```

**5. Se connecter** : http://localhost:3020 (Chrome)

| Utilisateur | Mot de passe | Rôle |
|---|---|---|
| `k.mweene`   | `test` | Registrar local (Ibombo) — voit les notifications OCR |
| `j.musonda`  | `test` | Registrar General |
| `j.campbell` | `test` | System admin (menu Configuration → Integrations) |

Code 2FA éventuel : `000000`.

## Envoyer un document OCR vers OpenCRVS

Depuis `C:\Users\Ghassen\Documents\gabon-ocr` (les identifiants d'intégration
sont dans `.env`, section `OPENCRVS_*`) :

```powershell
# traiter un scan puis l'envoyer :
.venv\Scripts\python.exe run_pipeline.py samples\mon_scan.jpg --backend gemini --out runs\mon_scan
.venv\Scripts\python.exe tools\send_to_opencrvs.py runs\mon_scan

# ou juste inspecter le payload sans envoyer :
.venv\Scripts\python.exe tools\send_to_opencrvs.py runs\mon_scan --dry-run
```

La déclaration pré-remplie apparaît dans la file **Notifications**
(connexion `k.mweene` — bureau d'Ibombo).

## Dépannage

- **Tâche bloquée en "Queued"** : c'était le mode batterie — déjà corrigé
  (`AllowStartIfOnBatteries`), mais si ça revient : brancher le PC ou
  ré-enregistrer la tâche.
- **Voir les logs** :
  ```powershell
  wsl -d ubuntu-opencrvs -u root -- tail -30 /var/log/opencrvs-services.log
  wsl -d ubuntu-opencrvs -u root -- tail -30 /var/log/opencrvs-countryconfig.log
  ```
- **countryconfig crash TypeScript** (`replaceAll ... type error`) : bug du code
  EY-DPI ; le script `/root/run_countryconfig.sh` contient déjà
  `TS_NODE_TRANSPILE_ONLY=true` qui le contourne.
- **Un seul service en panne** (ex. gateway à 000, le reste à 200) : nodemon
  affiche « app crashed - waiting for file changes ». Le relancer seul en
  touchant un fichier source (pas besoin de tout redémarrer) :
  ```powershell
  wsl -d ubuntu-opencrvs -u root -- touch /opt/opencrvs/opencrvs-core/packages/gateway/src/index.ts
  ```
  (remplacer `gateway` par le nom du service en panne)
- **Tâches tuées côté Windows mais processus Linux survivants** (symptôme :
  tâche « Ready » avec code 0xC000013A, certains ports répondent encore, d'autres
  sont à 000) : il suffit de relancer les tâches des services morts — les scripts
  `/root/run_<svc>.sh` contiennent un **guard d'idempotence** (posé par
  `tools/patch_run_scripts.sh`) qui tue les survivants du même package et libère
  le port avant `yarn start`. Un restart de tâche ne crée donc jamais de doublon
  (ni de watchers gen:types dupliqués qui corrompaient `schema.d.ts`).
  Si les scripts sont recréés un jour, ré-appliquer le patch :
  ```powershell
  wsl -d ubuntu-opencrvs -u root -- bash -c "tr -d '\r' < /mnt/c/Users/Ghassen/Documents/gabon-ocr/tools/patch_run_scripts.sh | bash"
  ```
- **JAMAIS `pkill -f node` dans la distro** pendant que le stack tourne :
  ça tue aussi les services core (leçon apprise…). Pour tout redémarrer
  proprement :
  ```powershell
  Stop-ScheduledTask opencrvs-services; Stop-ScheduledTask opencrvs-countryconfig
  wsl -d ubuntu-opencrvs -u root -- pkill -9 -f node
  Start-ScheduledTask opencrvs-services
  # attendre ~1 min puis :
  Start-ScheduledTask opencrvs-countryconfig
  ```
- **Git Bash + chemins WSL** : préfixer par `MSYS_NO_PATHCONV=1` sinon les
  chemins `/var/...` sont réécrits en `C:/Program Files/Git/var/...`.

## Arrêter proprement (avant d'éteindre)

Rien d'obligatoire — tout survit à un arrêt. Pour libérer la RAM sans éteindre :

```powershell
Stop-ScheduledTask opencrvs-services; Stop-ScheduledTask opencrvs-countryconfig
wsl --shutdown   # coupe aussi Docker Desktop
```

## Rappels d'architecture

- Dépôts : `/opt/opencrvs/opencrvs-core` (v1.9.14) et
  `/opt/opencrvs/opencrvs-countryconfig` (fork `Ghassenboussalem/…`, branche
  `main-poc`, remote `origin` = ton fork ; pour récupérer les mises à jour
  d'EY-DPI : `git remote add upstream https://github.com/EY-DPI/opencrvs-countryconfig` puis `git pull upstream main-poc`).
- Le mapping OCR → OpenCRVS est dans `pipeline/opencrvs_export.py`
  (seuil de confiance 0.6 ; tout le reste part en commentaire de revue).
- Migration vers l'instance du superviseur : il crée un client
  « Event notification » sur SON instance, puis remplacer les 4 URLs/identifiants
  `OPENCRVS_*` dans `.env` par les siens (URLs Tailscale). Aucun changement de code.
