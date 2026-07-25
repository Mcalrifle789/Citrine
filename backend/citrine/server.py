"""The Citrine backend: a FastAPI WebSocket server bound to loopback.

Security posture (spec §2.4): a localhost port is reachable by any local
process, and this backend gains desktop control in slice 4. So the first
frame must be a valid auth request, the Origin header is checked, and
failures close the socket before any other message is processed.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import uuid

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from citrine.app_status import app_status
from citrine.chat import send_chat
from citrine.commands import run_command
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


def create_app(token: str, allowed_origins: set[str]) -> FastAPI:
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

        await _serve(websocket)

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


async def _serve(websocket: WebSocket) -> None:
    """Message loop for an authenticated connection."""
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

        if envelope.method == "command.run":
            text = envelope.params.get("text", "")
            config = load_config()
            output = run_command(str(text), config)
            save_config(config)
            reply = make_envelope(envelope.id, MessageType.RESPONSE, "command.run",
                                  {"text": output})
            await websocket.send_text(reply.to_json())
            continue

        if envelope.method == "chat.send":
            text = envelope.params.get("text", "")
            reply = make_envelope(envelope.id, MessageType.RESPONSE, "chat.send",
                                  {"text": send_chat(str(text), load_config())})
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
    args = parser.parse_args()

    if args.host != "127.0.0.1":
        print("refusing to bind anything but loopback", file=sys.stderr)
        raise SystemExit(2)

    token = _require_token()
    app = create_app(token=token, allowed_origins=set(args.origin))

    config = uvicorn.Config(app, host=args.host, port=args.port,
                            log_config=None, access_log=False)
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
