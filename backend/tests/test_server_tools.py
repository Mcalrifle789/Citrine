"""Tools through the real WebSocket: the path the app actually uses.

``test_chat_tools.py`` calls ``send_chat`` directly. This module drives the
same work over an authenticated WebSocket through ``create_app``, which is
where the pieces meet: the workspace handed in at startup, the attachment
parser, the loop, and the ``tools_used`` field the renderer reads back.

The provider is still the scripted fake, so nothing here spends the user's
quota or depends on a network.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from citrine.server import create_app
from fake_provider import fake_provider, text_response, tool_response

TOKEN = "test-token-0123456789"
ORIGIN = "http://localhost:5173"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """An isolated CITRINE_HOME, so the user's real config is never read."""
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


def write_config(home, base_url: str) -> None:
    """Point the custom provider at the fake, with a key in the environment."""
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.json").write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "custom",
                        "label": "Custom",
                        "base_url": base_url,
                        "model": "test-model",
                    }
                ],
                "active_provider_id": "custom",
            }
        ),
        encoding="utf-8",
    )


def chat_frame(text: str, attachments=None, frame_id: str = "c1") -> str:
    return json.dumps(
        {
            "id": frame_id,
            "type": "request",
            "method": "chat.send",
            "params": {"text": text, "attachments": attachments or []},
        }
    )


def auth_frame() -> str:
    return json.dumps({"id": "a1", "type": "request", "method": "auth",
                       "params": {"token": TOKEN}})


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("CITRINE_CUSTOM_API_KEY", "test-key")


def test_a_tool_runs_and_is_reported_back_to_the_renderer(tmp_path, home, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("the answer is 42\n", encoding="utf-8")

    with fake_provider(
        [
            tool_response("read_file", {"path": "notes.txt"}),
            text_response("It says the answer is 42."),
        ]
    ) as running:
        write_config(home, running.base_url)
        app = create_app(token=TOKEN, allowed_origins={ORIGIN}, workspace=str(workspace))

        with TestClient(app) as client:
            with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
                ws.send_text(auth_frame())
                ws.receive_text()

                ws.send_text(chat_frame("what does notes.txt say?"))
                reply = json.loads(ws.receive_text())

    assert reply["method"] == "chat.send"
    assert reply["params"]["text"] == "It says the answer is 42."
    used = reply["params"]["tools_used"]
    assert len(used) == 1
    assert used[0]["name"] == "read_file"
    assert used[0]["ok"] is True
    assert used[0]["summary"].startswith("read_file") or used[0]["summary"]
    assert "the answer is 42" in running.requests_of("tool")[0]["content"]


def test_the_workspace_comes_from_the_server_not_the_process_cwd(tmp_path, home):
    """The tool reads from the workspace passed to create_app."""
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "marker.txt").write_text("workspace content\n", encoding="utf-8")

    with fake_provider(
        [
            tool_response("read_file", {"path": "marker.txt"}),
            text_response("found it"),
        ]
    ) as running:
        write_config(home, running.base_url)
        app = create_app(token=TOKEN, allowed_origins={ORIGIN}, workspace=str(workspace))

        with TestClient(app) as client:
            with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
                ws.send_text(auth_frame())
                ws.receive_text()
                ws.send_text(chat_frame("read marker.txt"))
                ws.receive_text()

    assert "workspace content" in running.requests_of("tool")[0]["content"]


def test_binary_attachment_reaches_the_model_as_bytes(tmp_path, home):
    payload = b"\x89PNG\r\n\x1a\n" + bytes(24)

    with fake_provider([text_response("I can see it.")]) as running:
        write_config(home, running.base_url)
        app = create_app(token=TOKEN, allowed_origins={ORIGIN}, workspace=str(tmp_path))

        with TestClient(app) as client:
            with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
                ws.send_text(auth_frame())
                ws.receive_text()
                ws.send_text(
                    chat_frame(
                        "what is this image?",
                        attachments=[
                            {
                                "name": "logo.png",
                                "size": len(payload),
                                "mime": "image/png",
                                "dataBase64": base64.b64encode(payload).decode(),
                                "truncated": False,
                            }
                        ],
                    )
                )
                reply = json.loads(ws.receive_text())

    assert reply["params"]["text"] == "I can see it."
    # Sent as a real image part, not as base64 text.
    content = running.requests[0]["messages"][1]["content"]
    assert isinstance(content, list)
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_a_command_runs_from_the_workspace(tmp_path, home):
    workspace = tmp_path / "project"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("x", encoding="utf-8")

    with fake_provider(
        [
            tool_response("run_command", {"command": "python -c \"import os; print(sorted(os.listdir('.')))\""}),
            text_response("Listed the directory."),
        ]
    ) as running:
        write_config(home, running.base_url)
        app = create_app(token=TOKEN, allowed_origins={ORIGIN}, workspace=str(workspace))

        with TestClient(app) as client:
            with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
                ws.send_text(auth_frame())
                ws.receive_text()
                ws.send_text(chat_frame("what is in this folder?"))
                ws.receive_text()

    assert "hello.txt" in running.requests_of("tool")[0]["content"]
