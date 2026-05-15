Option Explicit
' Investment Research App — silent Windows launcher
' Double-click this file (or a shortcut pointing to it) to start the app.

Dim WShell, http, alreadyUp

Set WShell = CreateObject("WScript.Shell")

' ── Check if Streamlit is already running ────────────────────────────────────
alreadyUp = False
On Error Resume Next
Set http = CreateObject("MSXML2.XMLHTTP.6.0")
http.Open "GET", "http://localhost:8501", False
http.Send
If Err.Number = 0 Then
    alreadyUp = (http.Status = 200)
End If
On Error GoTo 0

' ── Start Streamlit in WSL if not already running ────────────────────────────
If Not alreadyUp Then
    ' Hidden window (0), don't wait for it to finish (False)
    WShell.Run "wsl bash -c ""pgrep -f 'streamlit run app.py' > /dev/null 2>&1 || (cd /home/hchxie/projects/investment-agents && nohup python3 -m streamlit run app.py >> /tmp/streamlit_app.log 2>&1 &)""", 0, False
    ' Wait for server to come up (5 seconds)
    WScript.Sleep 5000
End If

' ── Open browser ─────────────────────────────────────────────────────────────
WShell.Run "http://localhost:8501", 1, False

Set WShell = Nothing
Set http   = Nothing
