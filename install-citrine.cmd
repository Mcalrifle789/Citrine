@echo off
rem Double-clickable installer for Citrine.
rem
rem This file MUST keep CRLF line endings - cmd.exe mis-parses LF-only batch
rem files, which silently breaks the PowerShell call below. Regenerate with
rem `python scripts/gen_wrappers.py` rather than editing by hand.
rem
rem Why this wrapper exists: double-clicking a .ps1 opens it in Notepad, and
rem "Run with PowerShell" closes the window before an error can be read. This
rem .cmd runs the real installer with a permissive execution policy, unblocks
rem the scripts if the repo arrived as a downloaded ZIP, and keeps the window
rem open so any error stays readable.
setlocal
title Citrine installer
cd /d "%~dp0"

if not exist "scripts\install.ps1" (
  echo ERROR: scripts\install.ps1 not found.
  echo Run this file from inside the Citrine repository folder.
  pause
  exit /b 1
)

echo Installing Citrine. This takes a minute or two.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -Path 'scripts\install.ps1' -ErrorAction SilentlyContinue; & 'scripts\install.ps1' @args; exit $LASTEXITCODE" %*
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo ================= INSTALL FAILED =================
  echo Read the red error above. If you ask for help, copy that line.
) else (
  echo ================= INSTALLED =================
  echo Start Citrine from the desktop shortcut, or type "citrine" in any NEW
  echo terminal window. First run: "citrine setup" to add your providers.
)
echo.
pause
exit /b %RC%
