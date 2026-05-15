@echo off
:: Investment Research App — one-click launcher
:: Run directly from a terminal for a visible window.
:: For a SILENT desktop launch (no black window), double-click launch.vbs instead.

setlocal

:: ── Port check: skip launch if Streamlit is already running ──────────────────
:: Uses PowerShell TCP socket — faster and more reliable than netstat
powershell -NoProfile -Command "try{$t=New-Object Net.Sockets.TcpClient('localhost',8501);$t.Close();exit 0}catch{exit 1}" >nul 2>&1

if %errorlevel% == 0 (
    echo Streamlit already running on port 8501 -- opening browser.
    start "" http://localhost:8501
    exit /b 0
)

:: ── Start Streamlit inside WSL (detached, logs to /tmp/streamlit_app.log) ────
:: nohup + & ensures the process survives after bash exits
echo Starting Streamlit in WSL Ubuntu...
wsl.exe -d Ubuntu -- bash -c "cd ~/projects/investment-agents && source ~/.bashrc && nohup streamlit run app.py --server.headless true >> /tmp/streamlit_app.log 2>&1 &"

:: ── Wait for the server to come up (4 seconds) ───────────────────────────────
echo Waiting for server...
timeout /t 4 /nobreak >nul

:: ── Open default browser ─────────────────────────────────────────────────────
echo Opening http://localhost:8501
start "" http://localhost:8501

endlocal
