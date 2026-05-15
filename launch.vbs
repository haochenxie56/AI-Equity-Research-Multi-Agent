Option Explicit
' Investment Research App — silent Windows launcher
' ─────────────────────────────────────────────────────────────────────────────
' HOW TO USE:
'   Desktop shortcut → right-click → Properties → Target: wscript.exe "C:\path\to\launch.vbs"
'   Or just double-click this .vbs file directly.
'   Do NOT point the shortcut at launch.bat (that shows a black cmd window).
' ─────────────────────────────────────────────────────────────────────────────

Dim WShell, fso, http, batPath, alreadyUp

Set WShell = CreateObject("WScript.Shell")
Set fso    = CreateObject("Scripting.FileSystemObject")

' ── Check if Streamlit is already up (avoid double-launch / port conflict) ────
alreadyUp = False
On Error Resume Next
Set http = CreateObject("MSXML2.XMLHTTP.6.0")
http.Open "GET", "http://localhost:8501/_stcore/health", False
http.Send
If Err.Number = 0 Then
    alreadyUp = (http.Status = 200)
End If
On Error GoTo 0
Set http = Nothing

If alreadyUp Then
    ' Already running — open the browser immediately, nothing else to do
    WShell.Run "http://localhost:8501", 1, False
Else
    ' Not running — call launch.bat silently:
    '   windowStyle = 0  → hidden (no black cmd window)
    '   waitOnReturn = False → VBS exits right away; bat runs in background
    batPath = fso.GetParentFolderName(WScript.ScriptFullName) & "\launch.bat"
    WShell.Run "cmd.exe /c """ & batPath & """", 0, False
End If

Set WShell = Nothing
Set fso    = Nothing
