@echo off
title Create SHRUTI AI Desktop Shortcut
cd /d "%~dp0"

echo [*] Creating Desktop Shortcut for SHRUTI AI...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
  "$sc = $ws.CreateShortcut(\"$desktop\SHRUTI AI.lnk\"); " ^
  "$sc.TargetPath = (Join-Path '%~dp0' 'Run_Shruti.bat'); " ^
  "$sc.WorkingDirectory = '%~dp0'; " ^
  "$sc.Description = 'SHRUTI AI - Intelligent Voice Desktop Assistant'; " ^
  "$sc.Save();"

if %errorlevel% equ 0 (
    echo.
    echo ================================================================
    echo [SUCCESS] Desktop shortcut 'SHRUTI AI' created on your Desktop!
    echo You can now launch SHRUTI directly from your Windows Desktop.
    echo ================================================================
) else (
    echo [ERROR] Failed to create shortcut automatically.
)

echo.
pause
