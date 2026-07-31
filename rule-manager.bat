@echo off
title Civil Aviation Doc Audit - Rule Manager

echo ========================================
echo   Civil Aviation Doc Audit - Rule Manager
echo ========================================
echo.
echo Starting rule management API service...
echo.

:: Start Python service in background
start /B "" python "%~dp0scripts\rule_admin.py" --port 8765

:: Wait for service to start
echo Waiting for service to be ready...
timeout /t 3 /nobreak >nul

:: Open browser
echo Opening rule manager panel...
start "" http://127.0.0.1:8765/

echo.
echo ========================================
echo   Rule Manager is now running!
echo   URL: http://127.0.0.1:8765/
echo.
echo   Close this window to stop the service.
echo ========================================
echo.

pause