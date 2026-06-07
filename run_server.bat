@echo off
title Antigravity Trading Server

cd /d "%~dp0"

echo ====================================================
echo      Antigravity Trading Server Starting...
echo ====================================================
echo.
echo [INFO] Preparing server launch...
echo [INFO] Web browser dashboard will open in 3 seconds.
echo.

:: Launch browser in background
start "" "http://localhost:8080"

echo [EXEC] Starting NiceGUI Web Server (python main.py)...
echo ====================================================
echo.

python main.py

echo.
echo ====================================================
echo [WARNING] Server process terminated.
echo ====================================================
pause
