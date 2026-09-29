"""A scripted OpenAI-compatible provider, for tests.

Serves canned chat-completion responses from loopback so the agent loop can be
driven deterministically. Shared by the loop tests (which call ``send_chat``)
and the server tests (which drive the same path over the real WebSocket), so
both exercise one implementation of the fake rather than two drifting ones.

Usage:

    with fake_provider([tool_response("read_file", {"path": "a.txt"}), text_response("done")]) as base:
        ...
"""

from __future__ import annotations

import http.server
import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


def text_response(text: str, tokens: int = 11) -> dict:
    """A plain assistant answer."""
    return {
        "choices": [
            {"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
        ],
        "usage": {"total_tokens": tokens},
    }


def tool_response(name: str, arguments: dict, *, call_id: str = "call_1") -> dict:
    """A response asking for one tool call."""
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"total_tokens": 7},
    }


def error_response(status: int, message: str) -> dict:
    """A provider error, sent as an HTTP status."""
    return {"__status__": status, "__body__": {"error": {"message": message}}}


@dataclass
class FakeProvider:
    """The running server plus what it received."""

    base_url: str
    requests: list[dict] = field(default_factory=list)
    _server: http.server.ThreadingHTTPServer | None = None

    def requests_of(self, role: str) -> list[dict]:
        """Every message with a given role, across all requests."""
        collected = []
        for request in self.requests:
            collected.extend(
                message
                for message in request.get("messages", [])
                if message.get("role") == role
            )
        return collected


class _Handler(http.server.BaseHTTPRequestHandler):
    script: list[dict] = []
    requests: list[dict] = []

    def do_POST(self):  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        type(self).requests.append(body)

        response = (
            type(self).script.pop(0)
            if type(self).script
            else text_response("(the script for this provider ran out)")
        )

        status = response.get("__status__")
        if status:
            payload = json.dumps(response.get("__body__", {})).encode()
        else:
            payload = json.dumps(response).encode()
            status = 200

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep pytest output clean
        return


@contextmanager
def fake_provider(script: list[dict] | None = None) -> Iterator[FakeProvider]:
    """Start the provider, run the block, stop it."""
    _Handler.script = list(script or [])
    _Handler.requests = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake = FakeProvider(
        base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
        requests=_Handler.requests,
        _server=server,
    )
    try:
        yield fake
    finally:
        server.shutdown()
        server.server_close()
