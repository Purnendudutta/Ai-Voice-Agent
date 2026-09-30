@echo off
title SHRUTI AI - Voice Desktop Assistant
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ================================================================
echo         SHRUTI AI - Intelligent Voice Desktop Assistant
echo ================================================================
echo.

:: 1. Check for Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your Windows PATH!
    echo.
    echo Please install Python 3.10, 3.11, 3.12, or 3.13 from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Make sure to check the box:
    echo   "[X] Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Setup Virtual Environment
if not exist ".venv" (
    echo [*] Setting up Python virtual environment (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    echo [*] Installing dependencies (this only happens on first run)...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [WARNING] Some dependencies had warnings during install. Attempting to continue...
    )
) else (
    call .venv\Scripts\activate.bat
)

:: 3. Launch SHRUTI
echo [*] Starting SHRUTI Voice Agent...
echo [*] Opening desktop application window...
python main.py

if %errorlevel% neq 0 (
    echo.
    echo [NOTICE] SHRUTI shut down. Press any key to close this window.
    pause
)
