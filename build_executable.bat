@echo off
title Build SHRUTI AI Standalone Windows Executable
cd /d "%~dp0"

echo ================================================================
echo       Building SHRUTI Standalone Windows Executable (.exe)
echo ================================================================
echo.

:: Check PyInstaller
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Installing PyInstaller...
    pip install pyinstaller
)

echo [*] Compiling SHRUTI with PyInstaller...
pyinstaller --clean shruti.spec

if %errorlevel% equ 0 (
    echo.
    echo ================================================================
    echo [SUCCESS] Build complete!
    echo Standalone executable is ready at:
    echo   dist\ShrutiAI\ShrutiAI.exe
    echo.
    echo You can zip the "dist\ShrutiAI" folder and send it to friends!
    echo ================================================================
) else (
    echo.
    echo [ERROR] Build failed. Please inspect the log output above.
)

pause
