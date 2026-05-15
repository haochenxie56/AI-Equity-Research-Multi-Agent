@echo off
:: Investment Research App — one-click launcher
:: Run directly from a terminal for a visible window.
:: For a SILENT desktop launch (no black window), double-click launch.vbs instead.

setlocal

:: ── Port check: skip launch if Streamlit is already running ──────────────────
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -Command "try{$t=New-Object Net.Sockets.TcpClient('localhost',8501);$t.Close();exit 0}catch{exit 1}" >nul 2>&1

if %errorlevel% == 0 (
    echo Streamlit already running on port 8501 -- opening browser.
    start "" http://localhost:8501
    exit /b 0
)

:: ── Resolve WSL paths dynamically (no hardcoded username) ────────────────────
echo Detecting WSL environment...

for /f "delims=" %%i in ('%SystemRoot%\System32\wsl.exe -d Ubuntu -- bash -c "echo $HOME"') do set WSL_HOME=%%i
if "%WSL_HOME%"=="" (
    echo ERROR: Could not detect WSL home directory. Is Ubuntu installed?
    pause
    exit /b 1
)

:: streamlit 装在 ~/.local/bin/，用 WSL_HOME 拼接路径
set STREAMLIT_BIN=%WSL_HOME%/.local/bin/streamlit
:: 验证文件是否存在
%SystemRoot%\System32\wsl.exe -d Ubuntu -- bash -c "test -f %STREAMLIT_BIN%" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: streamlit not found at %STREAMLIT_BIN%
    echo Please run in WSL: pip install streamlit
    pause
    exit /b 1
)

echo WSL_HOME=%WSL_HOME%
echo STREAMLIT_BIN=%STREAMLIT_BIN%

:: ── Start Streamlit inside WSL (detached) ────────────────────────────────────
echo Starting Streamlit in WSL Ubuntu...
%SystemRoot%\System32\wsl.exe -d Ubuntu -- bash -c "cd %WSL_HOME%/projects/investment-agents && setsid nohup %STREAMLIT_BIN% run app.py --server.headless true > /tmp/streamlit_app.log 2>&1 &"

:: ── Wait for the server to come up (5 seconds) ───────────────────────────────
echo Waiting for server to start (up to 15 seconds)...
set /a count=0
:waitloop
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -Command "try{$t=New-Object Net.Sockets.TcpClient('localhost',8501);$t.Close();exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel% == 0 goto open
set /a count+=1
if %count% geq 15 goto open
timeout /t 1 /nobreak >nul
goto waitloop
:open

:: ── Open default browser ─────────────────────────────────────────────────────
echo Opening http://localhost:8501
start "" http://localhost:8501

endlocal
