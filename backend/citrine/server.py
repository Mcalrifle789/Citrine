"""The Citrine backend: a FastAPI WebSocket server bound to loopback.

Security posture (spec §2.4): a localhost port is reachable by any local
process, and this backend gains desktop control in slice 4. So the first
frame must be a valid auth request, the Origin header is checked, and
failures close the socket before any other message is processed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
import uuid

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from citrine.app_status import app_status
from citrine.attachments import describe, parse_attachments
from citrine.chat import send_chat
from citrine.commands import COMMANDS, run_command
from citrine.config import load_config, save_config
from citrine.logging import get_logger
from citrine.protocol import (
    SERVER_VERSION,
    ErrorCode,
    MessageType,
    make_envelope,
    parse_envelope,
)

log = get_logger("citrine.server")

CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN_ORIGIN = 4403


def create_app(
    token: str,
    allowed_origins: set[str],
    workspace: str | None = None,
) -> FastAPI:
    app = FastAPI(title="Citrine backend", version=SERVER_VERSION)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        origin = websocket.headers.get("origin")
        await websocket.accept()

        # Origin is advisory on non-browser clients but blocks the browser
        # attack path outright, which is the one we can actually close.
        if origin is not None and origin not in allowed_origins:
            log.warning("rejected connection from origin %s", origin)
            await websocket.close(code=CLOSE_FORBIDDEN_ORIGIN)
            return

        if not await _authenticate(websocket, token):
            return

        await _serve(websocket, workspace)

    return app


async def _authenticate(websocket: WebSocket, token: str) -> bool:
    """Consume the first frame and require it to be a valid auth request."""
    try:
        raw = await websocket.receive_text()
    except WebSocketDisconnect:
        return False

    try:
        envelope = parse_envelope(raw)
    except ValueError:
        log.warning("malformed first frame; closing")
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return False

    supplied = envelope.params.get("token")
    if envelope.method != "auth" or not isinstance(supplied, str):
        log.warning("first frame was %s, not auth; closing", envelope.method)
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return False

    # Constant-time comparison: the token is a session secret.
    if not secrets.compare_digest(supplied, token):
        log.warning("invalid token; closing")
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return False

    reply = make_envelope(
        envelope.id, MessageType.RESPONSE, "auth",
        {"ok": True, "server_version": SERVER_VERSION},
    )
    await websocket.send_text(reply.to_json())
    log.info("client authenticated")
    return True


async def _serve(websocket: WebSocket, workspace: str | None = None) -> None:
    """Message loop for an authenticated connection.

    ``workspace`` is the directory the app was told to treat as the project
    root; tools resolve their paths against it.
    """
    while True:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            log.info("client disconnected")
            return

        try:
            envelope = parse_envelope(raw)
        except ValueError as exc:
            await _send_error(websocket, "unknown", "unknown", str(exc))
            continue

        log.info("recv %s %s", envelope.method, envelope.id)

        if envelope.method == "echo":
            text = envelope.params.get("text", "")
            reply = make_envelope(envelope.id, MessageType.RESPONSE, "echo",
                                  {"text": text})
            await websocket.send_text(reply.to_json())
            continue

        if envelope.method == "app.status":
            reply = make_envelope(envelope.id, MessageType.RESPONSE, "app.status",
                                  app_status(load_config()))
            await websocket.send_text(reply.to_json())
            continue

        if envelope.method == "app.commands":
            # The renderer's "/" menu is built from this. Serving the registry
            # rather than letting the renderer keep its own copy means the menu
            # cannot offer a command the backend does not implement.
            reply = make_envelope(
                envelope.id, MessageType.RESPONSE, "app.commands",
                {
                    "commands": [
                        {"name": command.name, "description": command.description}
                        for command in COMMANDS
                    ]
                },
            )
            await websocket.send_text(reply.to_json())
            continue

        if envelope.method == "command.run":
            text = envelope.params.get("text", "")
            config = load_config()
            # A command can shell out or touch git, which blocks. Run it on a
            # worker thread so this coroutine stays free to answer the
            # WebSocket ping - see _run_blocking.
            output = await _run_blocking(run_command, str(text), config)
            # Deliberately not charged to the context window. A slash command
            # runs locally against config and never reaches the model, so it
            # spends no context - and estimating a charge for it made /new and
            # /reset report a non-zero count for a conversation with nothing in
            # it, which is the opposite of what those commands promise.
            save_config(config)
            reply = make_envelope(envelope.id, MessageType.RESPONSE, "command.run",
                                  {"text": output})
            await websocket.send_text(reply.to_json())
            continue

        if envelope.method == "chat.send":
            text = envelope.params.get("text", "")
            attachments = parse_attachments(envelope.params.get("attachments"))
            if attachments:
                log.info("chat.send with %s", describe(attachments))
            config = load_config()
            result = await _run_blocking(
                send_chat, str(text), config, attachments, workspace=workspace
            )
            config.add_session_tokens(result.tokens_used)
            save_config(config)
            for step in result.steps:
                log.info("tool %s ok=%s %s", step.name, step.ok, step.summary)
            reply = make_envelope(envelope.id, MessageType.RESPONSE, "chat.send",
                                  {
                                      "text": result.text,
                                      "tokens_used": result.tokens_used,
                                      "tools_used": [
                                          {
                                              "name": step.name,
                                              "ok": step.ok,
                                              "summary": step.summary,
                                          }
                                          for step in result.steps
                                      ],
                                  })
            await websocket.send_text(reply.to_json())
            continue

        await _send_error(
            websocket, envelope.id, envelope.method,
            f"unknown method: {envelope.method}",
        )


async def _send_error(
    websocket: WebSocket, envelope_id: str, method: str, message: str
) -> None:
    correlation_id = uuid.uuid4().hex[:6]
    log.warning("error %s (%s): %s", method, correlation_id, message)
    frame = make_envelope(
        envelope_id, MessageType.ERROR, method,
        {
            "code": ErrorCode.SERVER.value,
            "message": message,
            "correlation_id": correlation_id,
        },
    )
    await websocket.send_text(frame.to_json())


async def _run_blocking(func, /, *args, **kwargs):
    """Run synchronous work on a thread instead of on the event loop.

    ``send_chat`` and ``run_command`` are both blocking: the first makes
    synchronous HTTP calls to the provider and can legitimately take minutes
    across tool rounds, the second can shell out. Awaiting them inline stalls
    this coroutine, and a stalled coroutine cannot answer the WebSocket ping -
    so uvicorn tears the connection down mid-turn and the user sees the agent
    time out. Handing the work to a thread is what keeps the socket alive.
    """
    return await asyncio.to_thread(lambda: func(*args, **kwargs))


class _AnnouncingServer(uvicorn.Server):
    """A uvicorn server that announces its real port once the socket is bound.

    With ``--port 0`` the OS assigns the port, so it is unknowable until
    after bind. Overriding ``startup`` is the supported hook that runs at
    exactly that moment.

    The announcement is the only thing ever written to stdout, so Electron
    can parse it unambiguously; all logging goes to stderr.
    """

    async def startup(self, sockets: list | None = None) -> None:
        await super().startup(sockets=sockets)
        print(json.dumps({"event": "ready", "port": self._bound_port()}), flush=True)

    def _bound_port(self) -> int:
        for server in getattr(self, "servers", []):
            for sock in server.sockets:
                return int(sock.getsockname()[1])
        return self.config.port


def main() -> None:
    parser = argparse.ArgumentParser(description="Citrine backend")
    parser.add_argument("--host", default="127.0.0.1",
                        help="loopback only; never bind 0.0.0.0")
    parser.add_argument("--port", type=int, default=0,
                        help="0 lets the OS assign a free port")
    parser.add_argument("--origin", action="append", default=[],
                        help="allowed Origin header value; repeatable")
    parser.add_argument("--workspace", default=None,
                        help="project root the agent's tools operate in")
    args = parser.parse_args()

    if args.host != "127.0.0.1":
        print("refusing to bind anything but loopback", file=sys.stderr)
        raise SystemExit(2)

    token = _require_token()
    app = create_app(token=token, allowed_origins=set(args.origin),
                     workspace=args.workspace)

    # A turn can legitimately run for minutes across tool rounds. The default
    # 20s pong deadline would drop the socket in the middle of one, so the
    # client is given a full turn budget to answer before being declared gone.
    config = uvicorn.Config(app, host=args.host, port=args.port,
                            log_config=None, access_log=False,
                            ws_ping_interval=20.0, ws_ping_timeout=300.0)
    _AnnouncingServer(config).run()


def _require_token() -> str:
    token = os.environ.get("CITRINE_AUTH_TOKEN")
    if not token:
        print(
            "CITRINE_AUTH_TOKEN is not set. The backend refuses to run "
            "unauthenticated because it binds a local port.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return token


if __name__ == "__main__":
    main()
