# Demarre TOUT le stack OpenCRVS local + l'app OCR, et affiche l'etat en direct
# jusqu'a ce que tout soit vert. Idempotent : relancable sans risque.
#
#   powershell -ExecutionPolicy Bypass -File C:\Users\Ghassen\Documents\gabon-ocr\start-opencrvs.ps1
#
# (ou creer un raccourci vers cette commande sur le Bureau)

$ErrorActionPreference = 'SilentlyContinue'
$GABON = 'C:\Users\Ghassen\Documents\gabon-ocr'

function Ping-Url($url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
        return [int]$r.StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        return 0
    }
}

Write-Host ""
Write-Host "=== OpenCRVS local - demarrage ===" -ForegroundColor Cyan

# ---------- 1. Docker Desktop ----------
docker info *> $null
if (-not $?) {
    Write-Host "[1/4] Docker Desktop n'est pas lance - demarrage..." -ForegroundColor Yellow
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    $ok = $false
    for ($i = 0; $i -lt 36; $i++) {
        Start-Sleep -Seconds 5
        docker info *> $null
        if ($?) { $ok = $true; break }
    }
    if (-not $ok) { Write-Host "Docker ne demarre pas - lance Docker Desktop manuellement puis relance ce script." -ForegroundColor Red; exit 1 }
}
# `docker info` teste le moteur cote Windows, mais docker compose est lance
# DEPUIS la distro : l'integration WSL peut n'etre pas encore prete alors que
# le moteur repond deja. Sans cette attente, des conteneurs sortent en 127
# (commande introuvable) et les services qui en dependent meurent au demarrage.
$dockerWsl = $false
for ($i = 0; $i -lt 24; $i++) {
    wsl -d ubuntu-opencrvs -u root -- docker info *> $null
    if ($?) { $dockerWsl = $true; break }
    Start-Sleep -Seconds 5
}
if (-not $dockerWsl) {
    Write-Host "Docker n'est pas accessible depuis WSL : active l'integration WSL dans Docker Desktop (Settings > Resources > WSL integration), puis relance." -ForegroundColor Red
    exit 1
}
Write-Host "[1/4] Docker Desktop : OK" -ForegroundColor Green

# ---------- 2. Conteneurs de dependances ----------
wsl -d ubuntu-opencrvs -u root -- bash -c "cd /opt/opencrvs/opencrvs-core && docker compose -p opencrvs -f docker-compose.deps.yml -f docker-compose.dev-deps.yml up -d" *> $null

# `up -d` rend la main des que les conteneurs sont LANCES, pas quand ils
# acceptent des connexions. Demarrer les microservices tout de suite les fait
# echouer sur ECONNREFUSED ; nodemon affiche alors "waiting for file changes"
# et ne repart plus jamais tout seul. D'ou les memes six services bloques a
# chaque demarrage. On attend donc que l'infra reponde vraiment.
$infra = @{ 'mongo' = 27017; 'postgres' = 5432; 'redis' = 6379;
            'elasticsearch' = 9200; 'minio' = 3535; 'influxdb' = 8086 }
Write-Host "[2/4] Conteneurs lances - attente de leur disponibilite..." -ForegroundColor Yellow
$deadline = (Get-Date).AddMinutes(4)
$pending = @($infra.Keys)
while ($pending.Count -gt 0 -and (Get-Date) -lt $deadline) {
    $still = @()
    foreach ($name in $pending) {
        $port = $infra[$name]
        wsl -d ubuntu-opencrvs -u root -- bash -c "timeout 2 bash -c '</dev/tcp/127.0.0.1/$port' 2>/dev/null" *> $null
        if (-not $?) { $still += $name }
    }
    $pending = $still
    if ($pending.Count -gt 0) { Start-Sleep -Seconds 3 }
}
if ($pending.Count -gt 0) {
    Write-Host ("[2/4] Infra incomplete (" + ($pending -join ', ') + ") - on continue, les services seront relances si besoin.") -ForegroundColor Yellow
} else {
    Write-Host "[2/4] Conteneurs (mongo, elasticsearch, postgres...) : prets" -ForegroundColor Green
}

# ---------- 3. Taches planifiees ----------
# chaque service core tourne dans SA tache planifiee (plus de monolithe lerna
# qui meurt en laissant des orphelins) — scripts /root/run_<svc>.sh, logs
# /var/log/opencrvs-<svc>.log dans la distro
# NB : les run_<svc>.sh sont idempotents (guard pose par tools/patch_run_scripts.sh :
# tue les survivants du package + libere le port avant yarn start) — relancer une
# tache ne cree jamais de doublon
foreach ($t in 'auth', 'user-mgnt', 'workflow', 'search', 'metrics', 'notification',
               'config', 'documents', 'webhooks', 'events', 'gateway', 'client',
               'login', 'countryconfig') {
    Start-ScheduledTask -TaskName ('opencrvs-' + $t)
}
# l'app OCR (uvicorn) : enregistree au premier lancement.
# Lancee via tools\run_hidden.vbs : les taches tournent avec un logon
# Interactive, donc chaque wsl.exe / python.exe ouvrait sa propre console —
# une vingtaine de terminaux a chaque demarrage. Le lanceur VBS demarre le
# processus fenetre masquee et l'attend, donc la tache reste "Running" et
# Stop-ScheduledTask continue de fonctionner. (Masquer via un principal S4U
# demanderait une elevation ; ceci non.)
# pythonw.exe ne convient pas ici : uvicorn a besoin de vrais flux stdout et
# s'arrete immediatement sans eux.
if (-not (Get-ScheduledTask -TaskName 'gabonocr-webapp')) {
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    $webArg = '//nologo "' + $GABON + '\tools\run_hidden.vbs" "' + $GABON + '\.venv\Scripts\python.exe" -m uvicorn review.app:app --host 0.0.0.0 --port 8000'
    $a = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument $webArg -WorkingDirectory $GABON
    Register-ScheduledTask -TaskName 'gabonocr-webapp' -Action $a -Settings $s -Force | Out-Null
}
Start-ScheduledTask -TaskName 'gabonocr-webapp'
Write-Host "[3/4] Services (taches planifiees) : lances" -ForegroundColor Green

# ---------- 4. Attente du vert, avec auto-reparation ----------
Write-Host "[4/4] Attente des services (environ 1 min ; plus long au tout premier demarrage)..." -ForegroundColor Yellow
Write-Host ""

# nom -> url ; chaque service en panne est repare en relancant SA tache dediee
$checks = @(
    @{ n = 'auth';          u = 'http://localhost:4040/ping'; task = 'opencrvs-auth' },
    @{ n = 'user-mgnt';     u = 'http://localhost:3030/ping'; task = 'opencrvs-user-mgnt' },
    @{ n = 'workflow';      u = 'http://localhost:5050/ping'; task = 'opencrvs-workflow' },
    @{ n = 'search';        u = 'http://localhost:9090/ping'; task = 'opencrvs-search' },
    @{ n = 'metrics';       u = 'http://localhost:1050/ping'; task = 'opencrvs-metrics' },
    @{ n = 'notification';  u = 'http://localhost:2020/ping'; task = 'opencrvs-notification' },
    @{ n = 'config';        u = 'http://localhost:2021/ping'; task = 'opencrvs-config' },
    @{ n = 'documents';     u = 'http://localhost:9050/ping'; task = 'opencrvs-documents' },
    @{ n = 'webhooks';      u = 'http://localhost:2525/ping'; task = 'opencrvs-webhooks' },
    @{ n = 'events';        u = 'http://localhost:5555/ping'; task = 'opencrvs-events' },
    @{ n = 'gateway';       u = 'http://localhost:7070/ping'; task = 'opencrvs-gateway' },
    @{ n = 'countryconfig'; u = 'http://localhost:3040/ping'; task = 'opencrvs-countryconfig' },
    @{ n = 'client';        u = 'http://localhost:3000';      task = 'opencrvs-client' },
    @{ n = 'login';         u = 'http://localhost:3020';      task = 'opencrvs-login' },
    @{ n = 'appOCR';        u = 'http://localhost:8000/healthz'; task = 'gabonocr-webapp' }
)
$fixed = @{}
$deadline = (Get-Date).AddMinutes(12)
$healAfter = (Get-Date).AddSeconds(45)

while ($true) {
    $line = @()
    $allUp = $true
    foreach ($c in $checks) {
        $code = Ping-Url $c.u
        if ($code -eq 200) {
            $line += ($c.n + " OK")
        } else {
            $allUp = $false
            $line += ($c.n + " [" + $code + "]")
            # Auto-reparation. Un service qui echoue a joindre sa dependance
            # au demarrage laisse nodemon sur "waiting for file changes" : il
            # ne repart JAMAIS seul, attendre plus longtemps ne sert donc a
            # rien. On relance vite (45 s) et jusqu'a deux fois, au lieu
            # d'attendre quatre minutes pour une seule tentative.
            if ((Get-Date) -gt $healAfter -and $fixed[$c.n] -lt 2) {
                $fixed[$c.n] = [int]$fixed[$c.n] + 1
                Stop-ScheduledTask -TaskName $c.task
                Start-Sleep -Seconds 2
                Start-ScheduledTask -TaskName $c.task
                $line[-1] += ' (relance ' + $fixed[$c.n] + ')'
            }
        }
    }
    Write-Host ("  " + ($line -join '   '))
    if ($allUp) { break }
    if ((Get-Date) -gt $deadline) {
        Write-Host ""
        Write-Host "TIMEOUT - services encore en panne ci-dessus. Logs :" -ForegroundColor Red
        Write-Host "  wsl -d ubuntu-opencrvs -u root -- tail -30 /var/log/opencrvs-services.log"
        exit 1
    }
    Start-Sleep -Seconds 12
    # une relance a besoin d'une trentaine de secondes pour aboutir : on
    # repousse la fenetre de reparation pour ne pas relancer par-dessus
    if ($line -match 'relance') { $healAfter = (Get-Date).AddSeconds(40) }
}

Write-Host ""
Write-Host "=== TOUT EST VERT ===" -ForegroundColor Green
Write-Host "  OpenCRVS : http://localhost:3020   (k.mweene / test, 2FA 000000)"
Write-Host "  App OCR  : http://localhost:8000"
Write-Host ""

# ---------- 5. Verification de l'integration OCR -> OpenCRVS ----------
# un arret brutal du PC fait rollbacker Mongo : le client d'integration
# disparait et les UUIDs de lieux peuvent changer (HANDOFF.md 6.7)
$envPath = "$GABON\.env"
$envLines = Get-Content $envPath
$cid = (($envLines | Where-Object { $_ -match '^OPENCRVS_CLIENT_ID=' }) -replace '.*=', '')
$csec = (($envLines | Where-Object { $_ -match '^OPENCRVS_CLIENT_SECRET=' }) -replace '.*=', '')
$cloc = (($envLines | Where-Object { $_ -match '^OPENCRVS_LOCATION_ID=' }) -replace '.*=', '')

# 5a. l'UUID du bureau d'Ibombo doit etre celui de k.mweene
# La requete echoue quand Mongo a perdu ses utilisateurs : elle renvoie alors
# un message d'erreur, pas un identifiant. Sans controle, ce message finissait
# ecrit dans .env a la place de l'UUID (et l'ecriture en ASCII detruisait les
# accents du fichier). On n'ecrit donc que si le resultat est bien un UUID, et
# on preserve l'encodage UTF-8.
$office = (docker exec opencrvs-mongo1-1 mongo user-mgnt --quiet --eval "print(db.users.findOne({username:'k.mweene'}).primaryOfficeId)" 2>$null | Select-Object -Last 1)
$office = if ($office) { $office.Trim() } else { '' }
$isUuid = $office -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
if ($isUuid -and $cloc -and $office -ne $cloc.Trim()) {
    (Get-Content $envPath -Encoding UTF8) -replace "^OPENCRVS_LOCATION_ID=.*", "OPENCRVS_LOCATION_ID=$office" |
        Set-Content $envPath -Encoding UTF8
    Write-Host "  ! OPENCRVS_LOCATION_ID mis a jour dans .env (le seed Mongo a change l'UUID du bureau)" -ForegroundColor Yellow
} elseif (-not $isUuid) {
    Write-Host "  ! Bureau introuvable dans Mongo (base reinitialisee ?) - .env laisse intact." -ForegroundColor Yellow
    Write-Host "    Relancer le seed : Start-ScheduledTask opencrvs-seed"
}


# 5b. le client d'integration doit pouvoir obtenir un token
$tokenOk = $false
if ($cid -and $csec) {
    try {
        # les identifiants passent par la query string, pas par le corps :
        # envoyes en formulaire, l'auth les refuse et le script annoncait a
        # tort un client d'integration perdu (cf. pipeline/opencrvs_export.py)
        $tokenUrl = "http://localhost:4040/token?client_id=$cid&client_secret=$csec&grant_type=client_credentials"
        $null = Invoke-WebRequest -Uri $tokenUrl -Method POST -UseBasicParsing -TimeoutSec 10
        $tokenOk = $true
    } catch {}
}
if ($tokenOk) {
    Write-Host "  Integration OCR->OpenCRVS : token OK" -ForegroundColor Green
} else {
    Write-Host "  ! CLIENT D'INTEGRATION PERDU (rollback Mongo) - a recreer :" -ForegroundColor Red
    Write-Host "    1. http://localhost:3020 -> j.campbell / test (2FA 000000)"
    Write-Host "    2. Configuration -> Integrations -> Create client (type Event notification)"
    Write-Host "    3. Mettre le nouveau Client ID + Secret dans $envPath (OPENCRVS_CLIENT_ID/SECRET)"
}
Write-Host ""
