@echo off
:: Investment Research App - one-click launcher
:: Double-click for a visible terminal window.
:: Double-click launch.vbs for a completely silent launch (no window).

setlocal

:: --- Port check: skip launch if Streamlit is already running -----------------
%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -Command "try{$t=New-Object Net.Sockets.TcpClient('localhost',8501);$t.Close();exit 0}catch{exit 1}" >nul 2>&1

if %errorlevel% == 0 (
    echo Streamlit already running on port 8501 -- opening browser.
    start "" http://localhost:8501
    exit /b 0
)

:: --- Resolve WSL home directory (no hardcoded username) ----------------------
echo Detecting WSL environment...

for /f "usebackq delims=" %%i in (`%SystemRoot%\System32\wsl.exe -d Ubuntu -- bash -c "echo $HOME"`) do set WSL_HOME=%%i

if "%WSL_HOME%"=="" (
    echo ERROR: Could not detect WSL home directory. Is Ubuntu installed?
    pause
    exit /b 1
)

set STREAMLIT_BIN=%WSL_HOME%/.local/bin/streamlit

%SystemRoot%\System32\wsl.exe -d Ubuntu -- bash -c "test -f %STREAMLIT_BIN%" >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: streamlit not found at %STREAMLIT_BIN%
    echo Please run in WSL: pip install streamlit
    pause
    exit /b 1
)

echo WSL_HOME=%WSL_HOME%
echo STREAMLIT_BIN=%STREAMLIT_BIN%

:: --- Launch browser watcher in background ------------------------------------
start /b %SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe -NoProfile -WindowStyle Hidden -Command "$i=0;while($i -lt 30){try{$t=New-Object Net.Sockets.TcpClient('localhost',8501);$t.Close();Start-Process 'http://localhost:8501';break}catch{$i++;Start-Sleep 1}}"

:: --- Run Streamlit in the FOREGROUND of this cmd window ----------------------
:: wsl.exe blocks here until Streamlit exits.
:: Closing this window stops the server.
echo Starting Streamlit (close this window to stop the server)...
%SystemRoot%\System32\wsl.exe -d Ubuntu -- bash -c "cd %WSL_HOME%/projects/investment-agents && %STREAMLIT_BIN% run app.py --server.headless true 2>&1 | tee -a /tmp/streamlit_app.log"

echo.
echo Streamlit exited. See above for details.
pause
endlocal
