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
Write-Host "[1/4] Docker Desktop : OK" -ForegroundColor Green

# ---------- 2. Conteneurs de dependances ----------
wsl -d ubuntu-opencrvs -u root -- bash -c "cd /opt/opencrvs/opencrvs-core && docker compose -p opencrvs -f docker-compose.deps.yml -f docker-compose.dev-deps.yml up -d" *> $null
Write-Host "[2/4] Conteneurs (mongo, elasticsearch, postgres...) : lances" -ForegroundColor Green

# ---------- 3. Taches planifiees ----------
# chaque service core tourne dans SA tache planifiee (plus de monolithe lerna
# qui meurt en laissant des orphelins) — scripts /root/run_<svc>.sh, logs
# /var/log/opencrvs-<svc>.log dans la distro
foreach ($t in 'auth', 'user-mgnt', 'workflow', 'search', 'metrics', 'notification',
               'config', 'documents', 'webhooks', 'events', 'gateway', 'client',
               'login', 'countryconfig') {
    Start-ScheduledTask -TaskName ('opencrvs-' + $t)
}
# l'app OCR (uvicorn) : enregistree au premier lancement
if (-not (Get-ScheduledTask -TaskName 'gabonocr-webapp')) {
    $s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
    $a = New-ScheduledTaskAction -Execute "$GABON\.venv\Scripts\python.exe" -Argument '-m uvicorn review.app:app --port 8000' -WorkingDirectory $GABON
    Register-ScheduledTask -TaskName 'gabonocr-webapp' -Action $a -Settings $s -Force | Out-Null
}
Start-ScheduledTask -TaskName 'gabonocr-webapp'
Write-Host "[3/4] Services (taches planifiees) : lances" -ForegroundColor Green

# ---------- 4. Attente du vert, avec auto-reparation ----------
Write-Host "[4/4] Attente des services (3-5 min au premier demarrage)..." -ForegroundColor Yellow
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
$healAfter = (Get-Date).AddMinutes(4)

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
            # auto-reparation : une seule fois par service, apres 4 min
            if ((Get-Date) -gt $healAfter -and -not $fixed[$c.n]) {
                $fixed[$c.n] = $true
                Stop-ScheduledTask -TaskName $c.task
                Start-Sleep -Seconds 2
                Start-ScheduledTask -TaskName $c.task
                $line[-1] += ' (relance...)'
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
    Start-Sleep -Seconds 15
}

Write-Host ""
Write-Host "=== TOUT EST VERT ===" -ForegroundColor Green
Write-Host "  OpenCRVS : http://localhost:3020   (k.mweene / test, 2FA 000000)"
Write-Host "  App OCR  : http://localhost:8000"
Write-Host ""
