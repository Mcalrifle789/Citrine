"""Secret storage for API keys.

Citrine prefers the operating system credential store through ``keyring`` when
the package is available. Development machines without keyring fall back to a
local JSON file that is intentionally labelled as weaker storage.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from citrine.paths import citrine_home, ensure_dirs

SERVICE = "Citrine"


def secret_key(kind: str, item_id: str) -> str:
    return f"{kind}:{item_id}"


def store_secret(key: str, value: str) -> str:
    if _try_keyring_set(key, value):
        return "os-keyring"
    _fallback_set(key, value)
    return "local-fallback"


def load_secret(key: str) -> str | None:
    value = _try_keyring_get(key)
    if value:
        return value
    return _fallback_get(key)


def secret_fingerprint(value: str | None) -> str:
    if not value:
        return "not set"
    if len(value) <= 8:
        return "set"
    return f"{value[:4]}...{value[-4:]}"


def _try_keyring_set(key: str, value: str) -> bool:
    try:
        import keyring  # type: ignore

        keyring.set_password(SERVICE, key, value)
        return True
    except Exception:
        return False


def _try_keyring_get(key: str) -> str | None:
    try:
        import keyring  # type: ignore

        return keyring.get_password(SERVICE, key)
    except Exception:
        return None


def _fallback_path() -> Path:
    override = os.environ.get("CITRINE_SECRET_FALLBACK")
    if override:
        return Path(override).expanduser().resolve()
    return citrine_home() / "secrets.local.json"


def _fallback_set(key: str, value: str) -> None:
    ensure_dirs()
    path = _fallback_path()
    data = _read_fallback(path)
    data[key] = base64.b64encode(value.encode("utf-8")).decode("ascii")
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fallback_get(key: str) -> str | None:
    encoded = _read_fallback(_fallback_path()).get(key)
    if not encoded:
        return None
    try:
        return base64.b64decode(encoded).decode("utf-8")
    except Exception:
        return None


def _read_fallback(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in raw.items()}
