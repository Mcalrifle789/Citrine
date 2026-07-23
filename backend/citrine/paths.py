"""Cross-platform filesystem locations for Citrine.

Windows redirects the Documents folder (commonly to OneDrive), so the
location is read from the shell-folder registry rather than assumed to be
``~/Documents``. Every path is overridable by environment variable to keep
tests hermetic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = ".citrine"
PRODUCT_NAME = "Citrine"


def citrine_home() -> Path:
    """Application-private directory: config, logs, session database."""
    override = os.environ.get("CITRINE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / APP_DIR_NAME


def config_path() -> Path:
    return citrine_home() / "config.json"


def logs_dir() -> Path:
    return citrine_home() / "logs"


def sessions_db_path() -> Path:
    return citrine_home() / "sessions.sqlite3"


def documents_dir() -> Path:
    """The user's Documents folder, honouring Windows shell redirection."""
    override = os.environ.get("CITRINE_DOCUMENTS")
    if override:
        return Path(override).expanduser().resolve()

    if sys.platform == "win32":
        redirected = _windows_documents_dir()
        if redirected is not None:
            return redirected

    return Path.home() / "Documents"


def _windows_documents_dir() -> Path | None:
    """Read the real Documents location from the shell-folder registry.

    Returns None if the key is unreadable, letting the caller fall back.
    """
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "Personal")
    except OSError:
        return None

    expanded = os.path.expandvars(value)
    return Path(expanded).resolve() if expanded else None


def agents_dir() -> Path:
    """User-visible agent files. Slice 5 populates this."""
    return documents_dir() / PRODUCT_NAME / "Agents"


def ensure_dirs() -> None:
    """Create every directory Citrine writes to. Safe to call repeatedly."""
    for directory in (citrine_home(), logs_dir(), agents_dir()):
        directory.mkdir(parents=True, exist_ok=True)
