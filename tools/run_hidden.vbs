' Run any command without opening a console window.
'
' Companion to run_service_hidden.vbs, for the pieces that are not WSL
' services — currently the OCR web app. pythonw.exe is not an option there:
' uvicorn needs real stdout/stderr handles and exits immediately without
' them, so the console still has to exist, just not be visible.
'
'   cscript //nologo run_hidden.vbs <exe> [args...]
'
' Waits for the process (bWaitOnReturn = True) so the scheduled task stays
' Running for as long as the app does, keeping Stop-ScheduledTask working.

Option Explicit

Dim i, part, cmd, shell

If WScript.Arguments.Count < 1 Then
  WScript.Echo "usage: run_hidden.vbs <exe> [args...]"
  WScript.Quit 1
End If

cmd = ""
For i = 0 To WScript.Arguments.Count - 1
  part = WScript.Arguments(i)
  If InStr(part, " ") > 0 Then part = """" & part & """"
  If i = 0 Then cmd = part Else cmd = cmd & " " & part
Next

Set shell = CreateObject("WScript.Shell")
WScript.Quit shell.Run(cmd, 0, True)
