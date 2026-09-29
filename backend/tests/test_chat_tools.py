"""The agent loop: tool calls, fallbacks, and accounting.

A fake OpenAI-compatible provider runs on loopback and replays a scripted list
of responses. That is deliberate: the thing worth testing is the loop - does a
tool call actually get executed, does its result actually get sent back, does
the model's prose actually reach the user - and none of that is visible if the
HTTP layer is mocked away.

The provider is scripted rather than a real model so the tests are
deterministic and free. What a real model chooses to do is not under test here.
"""

from __future__ import annotations

import base64
import http.server
import json
import threading
from pathlib import Path

import pytest

from citrine.attachments import parse_attachments
from citrine.chat import send_chat
from citrine.config import CitrineConfig, ProviderConfig

pytestmark = pytest.mark.usefixtures("api_key")


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    """The custom provider reads its key from the environment."""
    monkeypatch.setenv("CITRINE_CUSTOM_API_KEY", "test-key")


class _Provider(http.server.BaseHTTPRequestHandler):
    """Replays scripted chat-completion responses, recording each request."""

    script: list[dict] = []
    requests: list[dict] = []

    def do_POST(self):  # noqa: N802 - http.server's interface
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        type(self).requests.append(body)

        response = type(self).script.pop(0) if type(self).script else _text_response("(no script left)")

        if response.get("__status__"):
            payload = json.dumps(response.get("__body__", {})).encode()
            self.send_response(response["__status__"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        payload = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        return


def _text_response(text: str, tokens: int = 11) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"total_tokens": tokens},
    }


def _tool_response(name: str, arguments: dict, *, call_id: str = "call_1") -> dict:
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


def _error_response(status: int, message: str) -> dict:
    return {"__status__": status, "__body__": {"error": {"message": message}}}


@pytest.fixture()
def provider():
    _Provider.script = []
    _Provider.requests = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()


def config_for(base_url: str, workspace: Path) -> CitrineConfig:
    cfg = CitrineConfig()
    cfg.providers = [
        ProviderConfig(id="custom", label="Custom", base_url=base_url, model="test-model")
    ]
    cfg.active_provider_id = "custom"
    cfg.tools.workspace_root = str(workspace)
    return cfg


class TestToolLoop:
    def test_runs_a_tool_then_answers_with_the_result(self, provider, tmp_path):
        """The capability the update was about, end to end."""
        (tmp_path / "data.txt").write_text("secret contents\n", encoding="utf-8")
        _Provider.script = [
            _tool_response("read_file", {"path": "data.txt"}),
            _text_response("The file says: secret contents"),
        ]

        result = send_chat("what is in data.txt?", config_for(provider, tmp_path))

        assert "secret contents" in result.text
        assert [step.name for step in result.steps] == ["read_file"]
        assert result.steps[0].ok

        # The tool result really was sent back to the provider.
        follow_up = _Provider.requests[1]
        tool_messages = [m for m in follow_up["messages"] if m["role"] == "tool"]
        assert len(tool_messages) == 1
        assert "secret contents" in tool_messages[0]["content"]
        assert tool_messages[0]["tool_call_id"] == "call_1"

    def test_offers_the_tool_schemas_to_the_provider(self, provider, tmp_path):
        _Provider.script = [_text_response("hi")]

        send_chat("hello", config_for(provider, tmp_path))

        sent = _Provider.requests[0]
        assert sent["tool_choice"] == "auto"
        names = {tool["function"]["name"] for tool in sent["tools"]}
        assert {"read_file", "run_command", "git", "fetch_url"} <= names

    def test_runs_several_rounds_of_tool_calls(self, provider, tmp_path):
        (tmp_path / "one.txt").write_text("one\n", encoding="utf-8")
        _Provider.script = [
            _tool_response("read_file", {"path": "one.txt"}, call_id="c1"),
            _tool_response("list_dir", {"path": "."}, call_id="c2"),
            _text_response("done"),
        ]

        result = send_chat("look around", config_for(provider, tmp_path))

        assert result.text == "done"
        assert [step.name for step in result.steps] == ["read_file", "list_dir"]

    def test_executes_a_real_command(self, provider, tmp_path):
        _Provider.script = [
            _tool_response("run_command", {"command": "python -c \"print('from shell')\""}),
            _text_response("ran it"),
        ]

        result = send_chat("run something", config_for(provider, tmp_path))

        assert result.steps[0].ok
        tool_message = [m for m in _Provider.requests[1]["messages"] if m["role"] == "tool"][0]
        assert "from shell" in tool_message["content"]

    def test_reports_a_failed_tool_without_aborting(self, provider, tmp_path):
        _Provider.script = [
            _tool_response("read_file", {"path": "missing.txt"}),
            _text_response("That file does not exist."),
        ]

        result = send_chat("read missing.txt", config_for(provider, tmp_path))

        assert not result.steps[0].ok
        assert result.text == "That file does not exist."

    def test_sums_token_usage_across_rounds(self, provider, tmp_path):
        _Provider.script = [
            _tool_response("list_dir", {"path": "."}),
            _text_response("done", tokens=13),
        ]

        result = send_chat("look", config_for(provider, tmp_path))

        assert result.tokens_used == 7 + 13

    def test_stops_after_the_round_cap(self, provider, tmp_path):
        cfg = config_for(provider, tmp_path)
        cfg.tools.max_rounds = 2
        _Provider.script = [
            _tool_response("list_dir", {"path": "."}, call_id="c1"),
            _tool_response("list_dir", {"path": "."}, call_id="c2"),
        ]

        result = send_chat("loop forever", cfg)

        assert len(result.steps) == 2
        assert "stopped after 2 rounds" in result.text

    def test_sends_no_tools_when_tools_are_disabled(self, provider, tmp_path):
        cfg = config_for(provider, tmp_path)
        cfg.tools.enabled = False
        _Provider.script = [_text_response("plain answer")]

        result = send_chat("hello", cfg)

        assert "tools" not in _Provider.requests[0]
        assert result.text == "plain answer"
        assert result.steps == ()

    def test_executes_a_tool_that_hallucinated_arguments(self, provider, tmp_path):
        _Provider.script = [
            _tool_response("read_file", {"nonexistent_param": 1}),
            _text_response("I got that wrong, let me retry."),
        ]

        result = send_chat("read it", config_for(provider, tmp_path))

        assert not result.steps[0].ok
        tool_message = [m for m in _Provider.requests[1]["messages"] if m["role"] == "tool"][0]
        assert "Bad arguments" in tool_message["content"]


class TestFallbacks:
    def test_retries_without_tools_when_the_provider_rejects_them(self, provider, tmp_path):
        _Provider.script = [
            _error_response(400, "tools are not supported for this model"),
            _text_response("answered without tools"),
        ]

        result = send_chat("hello", config_for(provider, tmp_path))

        assert result.text == "answered without tools"
        assert len(_Provider.requests) == 2
        assert "tools" in _Provider.requests[0]
        assert "tools" not in _Provider.requests[1]

    def test_retries_without_images_when_the_model_cannot_see(self, provider, tmp_path):
        png = b"\x89PNG\r\n\x1a\n" + bytes(16)
        attachment = parse_attachments(
            [
                {
                    "name": "shot.png",
                    "size": len(png),
                    "mime": "image/png",
                    "dataBase64": base64.b64encode(png).decode(),
                }
            ]
        )[0]

        _Provider.script = [
            _error_response(400, "image content parts are not supported"),
            _text_response("I cannot see the image, but I was told what it is."),
        ]

        result = send_chat("what is this?", config_for(provider, tmp_path), [attachment])

        assert "cannot see" in result.text
        assert len(_Provider.requests) == 2
        # The retry really dropped the image part and kept the description.
        retry_content = _Provider.requests[1]["messages"][1]["content"]
        assert isinstance(retry_content, str)
        assert "PNG image" in retry_content

    def test_surfaces_a_provider_error_that_is_not_retryable(self, provider, tmp_path):
        _Provider.script = [_error_response(401, "invalid api key")]

        result = send_chat("hello", config_for(provider, tmp_path))

        assert "authentication" in result.text
        assert len(_Provider.requests) == 1


class TestAttachmentsInTheLoop:
    def test_sends_an_image_as_a_content_part(self, provider, tmp_path):
        png = b"\x89PNG\r\n\x1a\n" + bytes(16)
        attachment = parse_attachments(
            [
                {
                    "name": "logo.png",
                    "size": len(png),
                    "mime": "image/png",
                    "dataBase64": base64.b64encode(png).decode(),
                }
            ]
        )[0]
        _Provider.script = [_text_response("nice logo")]

        send_chat("look at this", config_for(provider, tmp_path), [attachment])

        content = _Provider.requests[0]["messages"][1]["content"]
        assert isinstance(content, list)
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_describes_a_binary_file_in_the_prompt(self, provider, tmp_path):
        payload = b"%PDF-1.4 fake pdf body"
        attachment = parse_attachments(
            [
                {
                    "name": "doc.pdf",
                    "size": len(payload),
                    "mime": "application/pdf",
                    "dataBase64": base64.b64encode(payload).decode(),
                }
            ]
        )[0]
        _Provider.script = [_text_response("ok")]

        send_chat("read this", config_for(provider, tmp_path), [attachment])

        content = _Provider.requests[0]["messages"][1]["content"]
        assert isinstance(content, str)
        assert "PDF document" in content
        assert "base64" in content

    def test_keeps_a_text_attachment_as_text(self, provider, tmp_path):
        attachment = parse_attachments(
            [{"name": "notes.md", "size": 5, "mime": "text/markdown", "text": "# hi\n"}]
        )[0]
        _Provider.script = [_text_response("ok")]

        send_chat("summarise", config_for(provider, tmp_path), [attachment])

        content = _Provider.requests[0]["messages"][1]["content"]
        assert isinstance(content, str)
        assert "# hi" in content


class TestSystemPrompt:
    def test_tells_the_model_it_has_tools_and_where_it_is(self, provider, tmp_path):
        _Provider.script = [_text_response("ok")]

        send_chat("hi", config_for(provider, tmp_path))

        system = _Provider.requests[0]["messages"][0]["content"]
        assert "You have tools. Use them." in system
        assert str(tmp_path) in system
        assert "run_command" in system
