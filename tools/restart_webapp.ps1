# Redemarre proprement l'application web OCR.
#
# Stop-ScheduledTask tue le lanceur VBS mais pas le python qu'il a demarre :
# l'instance suivante ne peut alors pas prendre le port 8000, s'arrete, et
# l'ancienne continue de servir du code obsolete sans le moindre message.
# On libere donc le port explicitement avant de relancer.
#
#   powershell -ExecutionPolicy Bypass -File tools\restart_webapp.ps1

$ErrorActionPreference = 'SilentlyContinue'

Stop-ScheduledTask -TaskName 'gabonocr-webapp'
Start-Sleep -Seconds 2
Get-NetTCPConnection -LocalPort 8000 -State Listen |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Start-Sleep -Seconds 1
Start-ScheduledTask -TaskName 'gabonocr-webapp'

for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 2
    try {
        $null = Invoke-WebRequest -Uri 'http://localhost:8000/healthz' -UseBasicParsing -TimeoutSec 3
        Write-Host "App OCR : OK (http://localhost:8000)" -ForegroundColor Green
        exit 0
    } catch {}
}
Write-Host "App OCR : ne repond pas - voir la tache gabonocr-webapp" -ForegroundColor Red
exit 1
