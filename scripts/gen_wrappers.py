"""Regenerate the double-clickable .cmd wrappers with CRLF line endings.

Why a generator instead of hand-writing the files: cmd.exe mis-parses
batch files with LF-only line endings, and the editor/agent tooling in this
repo writes LF by default. Baking the CRLF conversion into a script means
the wrappers cannot silently regress to LF again.

Usage: python scripts/gen_wrappers.py
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INSTALL = r"""@echo off
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
"""

UNINSTALL = r"""@echo off
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
"""

WRAPPERS = {
    "install-citrine.cmd": INSTALL,
    "uninstall-citrine.cmd": UNINSTALL,
}


def main() -> int:
    for name, text in WRAPPERS.items():
        # Normalise to CRLF regardless of how the string literal was written.
        body = text.replace("\r\n", "\n").replace("\n", "\r\n")
        target = ROOT / name
        target.write_bytes(body.encode("ascii"))
        print(f"wrote {name} ({len(body)} bytes, CRLF)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
