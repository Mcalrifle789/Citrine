import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from citrine.commands import COMMANDS
from citrine.protocol import MessageType, parse_envelope
from citrine.server import create_app

TOKEN = "test-token-0123456789"
ORIGIN = "http://localhost:5173"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path / "home"))
    # Commands like /init and /github resolve paths against the working
    # directory, so the suite runs from a scratch directory. Without this a
    # test that exercises them scaffolds a git repository into the source tree.
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
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


def test_app_status_reports_defaults(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "s1", "type": "request",
                                 "method": "app.status",
                                 "params": {}}))
        reply = parse_envelope(ws.receive_text())
        assert reply.id == "s1"
        assert reply.params["provider"] == "Not configured"
        assert reply.params["tokens"] == "--"
        assert reply.params["sessions"] == ["main"]
        assert "openai/gpt-5" in reply.params["models"]


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
        assert reply.params["tokens_used"] > 0

        ws.send_text(json.dumps({"id": "s2", "type": "request",
                                 "method": "app.status",
                                 "params": {}}))
        status = parse_envelope(ws.receive_text())
        assert status.params["token_used"] == reply.params["tokens_used"]


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


def test_app_commands_serves_the_backend_registry(client):
    """The renderer's "/" menu is built from this rather than a second copy,
    so it cannot offer a command the backend does not implement."""
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "k1", "type": "request",
                                 "method": "app.commands", "params": {}}))
        reply = parse_envelope(ws.receive_text())

        assert reply.id == "k1"
        commands = reply.params["commands"]
        assert len(commands) == len(COMMANDS)
        assert {"name", "description"} == set(commands[0])


def test_every_advertised_command_is_handled(client):
    """The menu offers all of these, so none of them may fall through to the
    unknown-command reply."""
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        for index, command in enumerate(COMMANDS):
            ws.send_text(json.dumps({"id": f"h{index}", "type": "request",
                                     "method": "command.run",
                                     "params": {"text": f"/{command.name}"}}))
            reply = parse_envelope(ws.receive_text())
            assert "Unknown command" not in reply.params["text"], command.name


def test_chat_send_accepts_attachments(client):
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({
            "id": "f1", "type": "request", "method": "chat.send",
            "params": {
                "text": "explain this",
                "attachments": [{"name": "main.py", "size": 12, "mime": "text/x-python",
                                 "text": "print(1)", "truncated": False}],
            },
        }))
        reply = parse_envelope(ws.receive_text())
        assert reply.id == "f1"
        assert reply.type is MessageType.RESPONSE


def test_a_malformed_attachment_does_not_break_the_turn(client):
    """A bad attachment should cost the user that file, not their message."""
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({
            "id": "f2", "type": "request", "method": "chat.send",
            "params": {"text": "still works", "attachments": "not a list"},
        }))
        reply = parse_envelope(ws.receive_text())
        assert reply.type is MessageType.RESPONSE
        assert "provider" in reply.params["text"].lower()


def test_a_bare_init_does_not_create_anything(client, tmp_path):
    """/init writes to disk and runs git. A bare verb must not do that to
    whatever directory the backend happened to be started in."""
    workspace = tmp_path / "workspace"
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(_auth_frame())
        ws.receive_text()
        ws.send_text(json.dumps({"id": "i1", "type": "request",
                                 "method": "command.run",
                                 "params": {"text": "/init"}}))
        reply = parse_envelope(ws.receive_text())

        assert "Usage" in reply.params["text"]
        assert not (workspace / ".git").exists()
        assert list(workspace.iterdir()) == []
