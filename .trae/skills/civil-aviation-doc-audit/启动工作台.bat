@echo off
REM ============================================================
REM  Workbench launcher (v10)
REM  Why http:// instead of file:// :
REM    showDirectoryPicker() and fetch() require a secure context.
REM    file:// is NOT a secure context, so the workbench must be
REM    served over http:// from localhost.
REM  What it does:
REM    1. serve .\workbench on http://localhost:8765
REM    2. open the default browser at the workbench entry
REM ============================================================
setlocal
set "PORT=8765"

REM --- pick a Python (chain detection, no hard-coded path) ---
set "PYCMD="
python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD (
    py -3 --version >nul 2>&1 && set "PYCMD=py -3"
)
if not defined PYCMD (
    echo [ERROR] Python not found in PATH. Install Python 3 and retry.
    pause
    exit /b 1
)

REM --- workbench bundle lives next to this script ---
if not exist "%~dp0workbench\index.html" (
    echo [ERROR] workbench\index.html not found next to this script.
    echo          Run the sync script first to deploy the workbench.
    pause
    exit /b 1
)
cd /d "%~dp0workbench"

REM --- reuse a running server if the port is already listening ---
netstat -ano | findstr /r ":%PORT%  *[^ ]*  *[^ ]*  *LISTENING" >nul 2>&1
if errorlevel 1 (
    start "workbench-server" /min cmd /c "%PYCMD% -m http.server %PORT%"
    timeout /t 1 /nobreak >nul
)

start "" "http://localhost:%PORT%/index.html"
endlocal
