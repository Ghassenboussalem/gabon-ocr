# Stop the OpenCRVS scheduled tasks from opening a console window each.
#
# The tasks run with an Interactive logon, so every wsl.exe / python.exe they
# launch pops its own terminal: about twenty per startup, and closing one by
# mistake kills the service it hosts. Repointing each action at a VBS
# launcher (WshShell.Run with window style 0) hides them without elevation —
# switching the task principal to S4U would work too, but needs admin.
#
# Each launcher waits on its process, so the task still reports Running and
# Stop-ScheduledTask still stops the service.
#
#   powershell -ExecutionPolicy Bypass -File tools\hide_service_windows.ps1
#
# Idempotent: safe to re-run, and worth re-running if the tasks are ever
# re-registered.

$GABON = Split-Path -Parent $PSScriptRoot
$svcLauncher = Join-Path $GABON 'tools\run_service_hidden.vbs'
$cmdLauncher = Join-Path $GABON 'tools\run_hidden.vbs'

$services = 'auth', 'user-mgnt', 'workflow', 'search', 'metrics', 'notification',
            'config', 'documents', 'webhooks', 'events', 'gateway', 'client',
            'login', 'countryconfig'

foreach ($s in $services) {
    $task = 'opencrvs-' + $s
    if (-not (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue)) {
        Write-Host ("  {0,-24} absente - ignoree" -f $task) -ForegroundColor DarkGray
        continue
    }
    $a = New-ScheduledTaskAction -Execute 'wscript.exe' `
        -Argument ('//nologo "' + $svcLauncher + '" ' + $s)
    try {
        Set-ScheduledTask -TaskName $task -Action $a -ErrorAction Stop | Out-Null
        Write-Host ("  {0,-24} OK" -f $task) -ForegroundColor Green
    } catch {
        Write-Host ("  {0,-24} ECHEC : {1}" -f $task, $_.Exception.Message) -ForegroundColor Red
    }
}

# the OCR web app is a plain Windows process, not a WSL service. pythonw.exe
# is not usable: uvicorn needs real stdout handles and exits without them.
if (Get-ScheduledTask -TaskName 'gabonocr-webapp' -ErrorAction SilentlyContinue) {
    $webArg = '//nologo "' + $cmdLauncher + '" "' + $GABON +
              '\.venv\Scripts\python.exe" -m uvicorn review.app:app --host 0.0.0.0 --port 8000'
    $a = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument $webArg -WorkingDirectory $GABON
    try {
        Set-ScheduledTask -TaskName 'gabonocr-webapp' -Action $a -ErrorAction Stop | Out-Null
        Write-Host ("  {0,-24} OK" -f 'gabonocr-webapp') -ForegroundColor Green
    } catch {
        Write-Host ("  {0,-24} ECHEC : {1}" -f 'gabonocr-webapp', $_.Exception.Message) -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Les services redemarres n'ouvriront plus de terminal." -ForegroundColor Cyan
Write-Host "Relancer start-opencrvs.ps1 pour appliquer aux services deja lances."
