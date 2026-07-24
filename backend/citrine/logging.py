"""Structured logging with key redaction enforced at the logger.

Redaction is applied by a filter rather than at call sites: a rule enforced
in one place cannot be forgotten in fifty.
"""

from __future__ import annotations

import logging
import re
import sys

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r'(?i)("(?:token|api_key|secret|password)"\s*:\s*")[^"]{8,}(")'),
)

REDACTION = "[REDACTED]"


def redact(text: str) -> str:
    """Strip anything that looks like credential material."""
    result = text
    result = _PATTERNS[3].sub(rf"\1{REDACTION}\2", result)
    for pattern in _PATTERNS[:3]:
        result = pattern.sub(REDACTION, result)
    return result


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if record.args:
            record.args = tuple(
                redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(_RedactingFilter())
    root = logging.getLogger("citrine")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    logger = logging.getLogger(name)
    logger.addFilter(_RedactingFilter())
    return logger
