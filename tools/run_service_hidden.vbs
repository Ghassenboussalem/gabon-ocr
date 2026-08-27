' Start one OpenCRVS WSL service without opening a console window.
'
' Each opencrvs-<svc> scheduled task used to run wsl.exe directly, and
' because the tasks run with an Interactive logon every one of them popped a
' terminal on the desktop — about twenty of them per startup. Hiding them by
' switching the task principal to S4U needs elevation; this launcher does not.
'
'   cscript //nologo run_service_hidden.vbs gateway
'
' WshShell.Run with window style 0 starts the process hidden, and waiting on
' it (bWaitOnReturn = True) keeps this script alive for as long as the
' service runs, so the scheduled task still shows as Running and
' Stop-ScheduledTask still stops the service.

Option Explicit

Dim svc, cmd, shell

If WScript.Arguments.Count < 1 Then
  WScript.Echo "usage: run_service_hidden.vbs <service-name>"
  WScript.Quit 1
End If

svc = WScript.Arguments(0)

cmd = "wsl.exe -d ubuntu-opencrvs -u root -- bash -c """ & _
      "bash /root/run_" & svc & ".sh > /var/log/opencrvs-" & svc & ".log 2>&1"""

Set shell = CreateObject("WScript.Shell")
WScript.Quit shell.Run(cmd, 0, True)
