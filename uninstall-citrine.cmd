@echo off
rem Double-clickable uninstaller for Citrine.
rem
rem This file MUST keep CRLF line endings - cmd.exe mis-parses LF-only batch
rem files. Regenerate with `python scripts/gen_wrappers.py`.
rem
rem Same wrapper rationale as install-citrine.cmd: reliable invocation, a
rem window that stays open, and readable errors. User data (config, logs and
rem sessions in ~\.citrine) is KEPT unless you add -PurgeData to the call
rem below. Add -DeleteSource to also delete the repository folder.
setlocal
title Citrine uninstaller
cd /d "%~dp0"

if not exist "scripts\uninstall.ps1" (
  echo ERROR: scripts\uninstall.ps1 not found.
  echo Run this file from inside the Citrine repository folder.
  pause
  exit /b 1
)

echo Uninstalling Citrine. Your config and session data are kept.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unblock-File -Path 'scripts\uninstall.ps1' -ErrorAction SilentlyContinue; & 'scripts\uninstall.ps1' @args; exit $LASTEXITCODE" %*
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo ================= UNINSTALL FAILED =================
  echo Read the red error above. If you ask for help, copy that line.
) else (
  echo ================= UNINSTALLED =================
)
echo.
pause
exit /b %RC%
