import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from citrine.protocol import MessageType, parse_envelope
from citrine.server import create_app

TOKEN = "test-token-0123456789"
ORIGIN = "http://localhost:5173"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path / "home"))
    app = create_app(token=TOKEN, allowed_origins={ORIGIN})
    return TestClient(app)


def _auth_frame(token: str = TOKEN) -> str:
    return json.dumps({"id": "a1", "type": "request", "method": "auth",
                       "params": {"token": token}})


def test_valid_token_is_accepted(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        reply = parse_envelope(ws.receive_text())
        assert reply.type is MessageType.RESPONSE
        assert reply.params["ok"] is True


def test_auth_reply_reuses_the_request_id(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        assert parse_envelope(ws.receive_text()).id == "a1"


def test_bad_token_closes_with_4401(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
            ws.send_text(_auth_frame("wrong-token"))
            ws.receive_text()
    assert excinfo.value.code == 4401


def test_non_auth_first_frame_closes_with_4401(client):
    """Auth must be the first frame; no other method is processed before it."""
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
            ws.send_text(json.dumps({"id": "e1", "type": "request",
                                     "method": "echo", "params": {"text": "hi"}}))
            ws.receive_text()
    assert excinfo.value.code == 4401


def test_malformed_first_frame_closes_with_4401(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
            ws.send_text("{not json")
            ws.receive_text()
    assert excinfo.value.code == 4401


def test_disallowed_origin_is_rejected(client):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"origin": "http://evil.example"}) as ws:
            ws.send_text(_auth_frame())
            ws.receive_text()
    assert excinfo.value.code == 4403


def test_echo_round_trips_after_authentication(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "e2", "type": "request", "method": "echo",
                                 "params": {"text": "hello spine"}}))
        reply = parse_envelope(ws.receive_text())
        assert reply.id == "e2"
        assert reply.params["text"] == "hello spine"


def test_command_run_returns_search_setup_guidance(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "c1", "type": "request",
                                 "method": "command.run",
                                 "params": {"text": "/searchsetup"}}))
        reply = parse_envelope(ws.receive_text())
        assert reply.id == "c1"
        assert "DuckDuckGo" in reply.params["text"]
        assert "Parallel Free" in reply.params["text"]


def test_command_run_returns_session_guidance(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "c2", "type": "request",
                                 "method": "command.run",
                                 "params": {"text": "/session"}}))
        reply = parse_envelope(ws.receive_text())
        assert "Sessions" in reply.params["text"]


def test_chat_send_reports_missing_provider(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "chat1", "type": "request",
                                 "method": "chat.send",
                                 "params": {"text": "hello"}}))
        reply = parse_envelope(ws.receive_text())
        assert reply.id == "chat1"
        assert "No model provider" in reply.params["text"]


def test_command_run_reports_unknown_commands(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "c3", "type": "request",
                                 "method": "command.run",
                                 "params": {"text": "/wat"}}))
        reply = parse_envelope(ws.receive_text())
        assert reply.params["text"].startswith("Unknown command: /wat")


def test_unknown_method_returns_an_error_frame_without_closing(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "u1", "type": "request",
                                 "method": "nonexistent", "params": {}}))
        reply = parse_envelope(ws.receive_text())
        assert reply.type is MessageType.ERROR
        assert reply.params["code"] == "server"
        assert reply.params["correlation_id"]

        # The connection survives: a later echo still works.
        ws.send_text(json.dumps({"id": "e3", "type": "request", "method": "echo",
                                 "params": {"text": "still here"}}))
        assert parse_envelope(ws.receive_text()).params["text"] == "still here"
