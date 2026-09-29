"""The agent loop: tool calls, fallbacks, and accounting.

A fake OpenAI-compatible provider (tests/fake_provider.py) replays a scripted
list of responses on loopback. That is deliberate: the thing worth testing is
the loop - does a tool call actually get executed, does its result actually get
sent back, does the model's prose actually reach the user - and none of that is
visible if the HTTP layer is mocked away.

The provider is scripted rather than a real model so the tests are
deterministic and free. What a real model chooses to do is not under test here.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from citrine.attachments import parse_attachments
from citrine.chat import send_chat
from citrine.config import CitrineConfig, ProviderConfig
from fake_provider import error_response, fake_provider, text_response, tool_response


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    """The custom provider reads its key from the environment."""
    monkeypatch.setenv("CITRINE_CUSTOM_API_KEY", "test-key")


def config_for(base_url: str, workspace: Path) -> CitrineConfig:
    cfg = CitrineConfig()
    cfg.providers = [
        ProviderConfig(id="custom", label="Custom", base_url=base_url, model="test-model")
    ]
    cfg.active_provider_id = "custom"
    cfg.tools.workspace_root = str(workspace)
    return cfg


def image_attachment(png: bytes):
    return parse_attachments(
        [
            {
                "name": "shot.png",
                "size": len(png),
                "mime": "image/png",
                "dataBase64": base64.b64encode(png).decode(),
            }
        ]
    )[0]


class TestToolLoop:
    def test_runs_a_tool_then_answers_with_the_result(self, tmp_path):
        """The capability this update was about, end to end."""
        (tmp_path / "data.txt").write_text("secret contents\n", encoding="utf-8")
        with fake_provider(
            [
                tool_response("read_file", {"path": "data.txt"}),
                text_response("The file says: secret contents"),
            ]
        ) as running:
            result = send_chat("what is in data.txt?", config_for(running.base_url, tmp_path))

            assert "secret contents" in result.text
            assert [step.name for step in result.steps] == ["read_file"]
            assert result.steps[0].ok

            # The tool result really was sent back to the provider.
            tool_messages = running.requests_of("tool")
            assert len(tool_messages) == 1
            assert "secret contents" in tool_messages[0]["content"]
            assert tool_messages[0]["tool_call_id"] == "call_1"

    def test_offers_the_tool_schemas_to_the_provider(self, tmp_path):
        with fake_provider([text_response("hi")]) as running:
            send_chat("hello", config_for(running.base_url, tmp_path))

            sent = running.requests[0]
            assert sent["tool_choice"] == "auto"
            names = {tool["function"]["name"] for tool in sent["tools"]}
            assert {"read_file", "run_command", "git", "fetch_url"} <= names

    def test_runs_several_rounds_of_tool_calls(self, tmp_path):
        (tmp_path / "one.txt").write_text("one\n", encoding="utf-8")
        with fake_provider(
            [
                tool_response("read_file", {"path": "one.txt"}, call_id="c1"),
                tool_response("list_dir", {"path": "."}, call_id="c2"),
                text_response("done"),
            ]
        ) as running:
            result = send_chat("look around", config_for(running.base_url, tmp_path))

            assert result.text == "done"
            assert [step.name for step in result.steps] == ["read_file", "list_dir"]

    def test_executes_a_real_command(self, tmp_path):
        with fake_provider(
            [
                tool_response("run_command", {"command": "python -c \"print('from shell')\""}),
                text_response("ran it"),
            ]
        ) as running:
            result = send_chat("run something", config_for(running.base_url, tmp_path))

            assert result.steps[0].ok
            tool_message = running.requests_of("tool")[0]
            assert "from shell" in tool_message["content"]

    def test_reports_a_failed_tool_without_aborting(self, tmp_path):
        with fake_provider(
            [
                tool_response("read_file", {"path": "missing.txt"}),
                text_response("That file does not exist."),
            ]
        ) as running:
            result = send_chat("read missing.txt", config_for(running.base_url, tmp_path))

            assert not result.steps[0].ok
            assert result.text == "That file does not exist."

    def test_sums_token_usage_across_rounds(self, tmp_path):
        with fake_provider(
            [
                tool_response("list_dir", {"path": "."}),
                text_response("done", tokens=13),
            ]
        ) as running:
            result = send_chat("look", config_for(running.base_url, tmp_path))

            assert result.tokens_used == 7 + 13

    def test_stops_after_the_round_cap(self, tmp_path):
        with fake_provider(
            [
                tool_response("list_dir", {"path": "."}, call_id="c1"),
                tool_response("list_dir", {"path": "."}, call_id="c2"),
            ]
        ) as running:
            cfg = config_for(running.base_url, tmp_path)
            cfg.tools.max_rounds = 2

            result = send_chat("loop forever", cfg)

            assert len(result.steps) == 2
            assert "stopped after 2 rounds" in result.text

    def test_sends_no_tools_when_tools_are_disabled(self, tmp_path):
        with fake_provider([text_response("plain answer")]) as running:
            cfg = config_for(running.base_url, tmp_path)
            cfg.tools.enabled = False

            result = send_chat("hello", cfg)

            assert "tools" not in running.requests[0]
            assert result.text == "plain answer"
            assert result.steps == ()

    def test_executes_a_tool_that_hallucinated_arguments(self, tmp_path):
        with fake_provider(
            [
                tool_response("read_file", {"nonexistent_param": 1}),
                text_response("I got that wrong, let me retry."),
            ]
        ) as running:
            result = send_chat("read it", config_for(running.base_url, tmp_path))

            assert not result.steps[0].ok
            assert "Bad arguments" in running.requests_of("tool")[0]["content"]


class TestFallbacks:
    def test_retries_without_tools_when_the_provider_rejects_them(self, tmp_path):
        with fake_provider(
            [
                error_response(400, "tools are not supported for this model"),
                text_response("answered without tools"),
            ]
        ) as running:
            result = send_chat("hello", config_for(running.base_url, tmp_path))

            assert result.text == "answered without tools"
            assert len(running.requests) == 2
            assert "tools" in running.requests[0]
            assert "tools" not in running.requests[1]

    def test_retries_without_images_when_the_model_cannot_see(self, tmp_path):
        png = b"\x89PNG\r\n\x1a\n" + bytes(16)
        with fake_provider(
            [
                error_response(400, "image content parts are not supported"),
                text_response("I cannot see the image, but I was told what it is."),
            ]
        ) as running:
            result = send_chat(
                "what is this?", config_for(running.base_url, tmp_path), [image_attachment(png)]
            )

            assert "cannot see" in result.text
            assert len(running.requests) == 2
            # The retry really dropped the image part and kept the description.
            retry_content = running.requests[1]["messages"][1]["content"]
            assert isinstance(retry_content, str)
            assert "PNG image" in retry_content

    def test_surfaces_a_provider_error_that_is_not_retryable(self, tmp_path):
        with fake_provider([error_response(401, "invalid api key")]) as running:
            result = send_chat("hello", config_for(running.base_url, tmp_path))

            assert "authentication" in result.text
            assert len(running.requests) == 1


class TestAttachmentsInTheLoop:
    def test_sends_an_image_as_a_content_part(self, tmp_path):
        png = b"\x89PNG\r\n\x1a\n" + bytes(16)
        with fake_provider([text_response("nice logo")]) as running:
            send_chat(
                "look at this", config_for(running.base_url, tmp_path), [image_attachment(png)]
            )

            content = running.requests[0]["messages"][1]["content"]
            assert isinstance(content, list)
            assert content[0]["type"] == "text"
            assert content[1]["type"] == "image_url"
            assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_describes_a_binary_file_in_the_prompt(self, tmp_path):
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
        with fake_provider([text_response("ok")]) as running:
            send_chat("read this", config_for(running.base_url, tmp_path), [attachment])

            content = running.requests[0]["messages"][1]["content"]
            assert isinstance(content, str)
            assert "PDF document" in content
            assert "base64" in content

    def test_keeps_a_text_attachment_as_text(self, tmp_path):
        attachment = parse_attachments(
            [{"name": "notes.md", "size": 5, "mime": "text/markdown", "text": "# hi\n"}]
        )[0]
        with fake_provider([text_response("ok")]) as running:
            send_chat("summarise", config_for(running.base_url, tmp_path), [attachment])

            content = running.requests[0]["messages"][1]["content"]
            assert isinstance(content, str)
            assert "# hi" in content


class TestSystemPrompt:
    def test_tells_the_model_it_has_tools_and_where_it_is(self, tmp_path):
        with fake_provider([text_response("ok")]) as running:
            send_chat("hi", config_for(running.base_url, tmp_path))

            system = running.requests[0]["messages"][0]["content"]
            assert "You have tools. Use them." in system
            assert str(tmp_path) in system
            assert "run_command" in system
