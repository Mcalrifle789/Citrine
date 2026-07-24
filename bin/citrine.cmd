@echo off
rem Citrine launcher. On PATH, so typing "citrine" in any terminal starts the
rem app. Holds the terminal and streams logs, exactly like `npm run dev`;
rem press Ctrl+C to stop. `%~dp0` is this file's folder (bin\), so `..` is the
rem repo root regardless of where the command was invoked from.
cd /d "%~dp0.."

if /I "%~1"=="setup" (
  shift
  cd /d "%~dp0..\backend"
  call uv run python -m citrine.setup_cli %*
  exit /b %ERRORLEVEL%
)

call npm run dev %*
