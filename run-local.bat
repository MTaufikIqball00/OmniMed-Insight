@echo off
REM OmniMed Insight (XAI) — Quick Windows Batch Launcher
REM Forwards arguments to run-local.ps1 with ExecutionPolicy Bypass
title OmniMed Insight (XAI)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-local.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [Launcher] An error occurred during startup.
    pause
)
