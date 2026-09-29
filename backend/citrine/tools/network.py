"""The network, as a tool.

One tool - ``fetch_url`` - because it covers what the agent actually needs in a
conversation: read a page, call an API, post a payload. A browser engine is a
different project.

Constraints worth knowing: http and https only (no ``file:`` or ``ftp:``, which
would turn a web tool into a local file reader by another route), a response
cap, and a timeout. Responses are decoded as text when they look like text and
described the same way a binary file is otherwise, so fetching a PDF returns
something the model can reason about instead of a wall of mojibake.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from citrine.tools.base import ToolContext, ToolResult, truncate, format_bytes
from citrine.tools import magic

DEFAULT_TIMEOUT_S = 30
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 40_000

ALLOWED_SCHEMES = {"http", "https"}


def fetch_url(
    url: str,
    ctx: ToolContext,
    *,
    method: str = "GET",
    headers: dict | None = None,
    body: str | None = None,
    timeout_s: int | None = None,
) -> ToolResult:
    """Make an HTTP request and return the response as text."""
    if not ctx.allow_network:
        return ToolResult.failure("network access is disabled (tools.allow_network is false)")

    target = (url or "").strip()
    if not target:
        return ToolResult.failure("No URL given.")

    parsed = urllib.parse.urlparse(target)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return ToolResult.failure(
            f"Refused: only http and https URLs are allowed, got {parsed.scheme or 'no'} scheme."
        )
    if not parsed.netloc:
        return ToolResult.failure(f"Not a valid URL: {target}")

    request_headers = {"User-Agent": "Citrine/0.1 (local agent)"}
    if isinstance(headers, dict):
        request_headers.update({str(key): str(value) for key, value in headers.items()})

    payload = None
    if body is not None:
        payload = body.encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = urllib.request.Request(
        target,
        data=payload,
        headers=request_headers,
        method=(method or "GET").upper(),
    )

    timeout = max(1, timeout_s or DEFAULT_TIMEOUT_S)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read(MAX_RESPONSE_BYTES)
            truncated = response.length is not None and response.length > len(raw)
            status = response.status
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        detail = _render_body(exc.read(64 * 1024), exc.headers.get("Content-Type", ""))
        return ToolResult.failure(
            truncate(
                f"{target}\n[http {exc.code} {exc.reason}]\n{detail}",
                MAX_TEXT_CHARS,
                note="error body truncated",
            )
        )
    except urllib.error.URLError as exc:
        return ToolResult.failure(f"{target}\n[network error: {exc.reason}]")
    except TimeoutError:
        return ToolResult.failure(f"{target}\n[timed out after {timeout}s]")
    except OSError as exc:
        return ToolResult.failure(f"{target}\n[request failed: {exc}]")

    header = (
        f"{target}\n[http {status}, {content_type or 'unknown content type'}, "
        f"{format_bytes(len(raw))}{' (capped)' if truncated else ''}]"
    )
    return ToolResult.success(f"{header}\n{_render_body(raw, content_type)}")


def _render_body(raw: bytes, content_type: str) -> str:
    """Text when it is text, a description when it is not."""
    text = magic.decode_text(raw)

    if text is not None:
        stripped = text.lstrip()
        if "json" in content_type.lower() or stripped.startswith(("{", "[")):
            # Normalise so a minified API response is readable rather than one
            # very long line.
            try:
                pretty = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
                text = pretty
            except (ValueError, TypeError):
                pass
        return truncate(text, MAX_TEXT_CHARS, note="response truncated")

    return truncate(magic.describe_binary(raw), MAX_TEXT_CHARS, note="response truncated")
