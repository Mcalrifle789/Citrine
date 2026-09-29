"""Why a turn used to look like it had hung, and what now stops it.

The reported symptom was "my agent keeps timing out". There were three causes
stacked on top of each other, and each needs its own guard:

1. ``send_chat`` and ``run_command`` are synchronous. Awaiting them inline in
   the WebSocket handler stalled the event loop, so uvicorn could not answer
   its own keepalive ping and dropped the socket mid-turn. Fixed by running
   them on a worker thread.
2. A turn was bounded only by ``max_rounds * request_timeout``, which on the
   defaults is long enough to be indistinguishable from a hang. Fixed with a
   wall-clock budget across the whole turn.
3. A provider read timeout reported itself as a network error, which reads as
   "you are offline" when the machine plainly is not.
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest
from fastapi.testclient import TestClient

from citrine import chat, server
from citrine.chat import send_chat
from citrine.config import CitrineConfig, ProviderConfig
from citrine.protocol import parse_envelope
from fake_provider import fake_provider, text_response, tool_response

TOKEN = "test-token-0123456789"
ORIGIN = "http://localhost:5173"


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("CITRINE_CUSTOM_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Keep these tests off the developer's real config file."""
    monkeypatch.setattr(
        "citrine.config.config_path", lambda: tmp_path / "config.json"
    )


def config_for(base_url: str) -> CitrineConfig:
    cfg = CitrineConfig()
    cfg.providers = [
        ProviderConfig(id="custom", label="Custom", base_url=base_url, model="test-model")
    ]
    cfg.active_provider_id = "custom"
    return cfg


def auth_frame(token: str = TOKEN) -> str:
    return json.dumps(
        {"id": "a1", "type": "request", "method": "auth", "params": {"token": token}}
    )


# ------------------------------------------------- the loop stays responsive


def test_blocking_work_yields_the_event_loop():
    """The keepalive bug, at the seam that fixes it.

    ``_run_blocking`` exists so a turn does not hold the event loop. If it ever
    calls its argument inline again, the ticker below never advances - and that
    is exactly the condition under which uvicorn cannot answer its own
    WebSocket ping and drops the socket mid-turn.
    """
    started = threading.Event()
    release = threading.Event()
    ticks = 0

    def blocking_work() -> str:
        started.set()
        assert release.wait(timeout=10), "the event loop never got a turn"
        return "done"

    async def scenario() -> str:
        nonlocal ticks

        async def ticker() -> None:
            nonlocal ticks
            while not release.is_set():
                ticks += 1
                await asyncio.sleep(0.005)

        async def unblock() -> None:
            # Only reachable if the loop is free while blocking_work runs.
            while not started.is_set():
                await asyncio.sleep(0.005)
            await asyncio.sleep(0.05)
            release.set()

        beat = asyncio.ensure_future(ticker())
        free = asyncio.ensure_future(unblock())
        result = await server._run_blocking(blocking_work)
        await free
        await beat
        return result

    assert asyncio.run(asyncio.wait_for(scenario(), timeout=15)) == "done"
    assert ticks > 1, "the event loop was starved for the whole call"


def test_run_blocking_passes_arguments_through():
    async def scenario():
        return await server._run_blocking(lambda a, b=0: a + b, 2, b=3)

    assert asyncio.run(scenario()) == 5


def test_run_blocking_propagates_the_failure():
    """A tool crash has to surface as an error frame, not be swallowed."""

    def boom():
        raise RuntimeError("nope")

    async def scenario():
        return await server._run_blocking(boom)

    with pytest.raises(RuntimeError, match="nope"):
        asyncio.run(scenario())


def test_a_turn_is_dispatched_off_the_event_loop(monkeypatch):
    """The seam is only useful if chat.send actually goes through it."""
    dispatched: list[object] = []

    async def spy(func, /, *args, **kwargs):
        dispatched.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(server, "_run_blocking", spy)
    monkeypatch.setattr(server, "send_chat", lambda *a, **k: chat.ChatResult("hi", 3))
    client = TestClient(server.create_app(token=TOKEN, allowed_origins={ORIGIN}))

    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(auth_frame())
        ws.receive_text()
        ws.send_text(
            json.dumps(
                {
                    "id": "chat1",
                    "type": "request",
                    "method": "chat.send",
                    "params": {"text": "hello"},
                }
            )
        )
        assert parse_envelope(ws.receive_text()).params["text"] == "hi"

    assert dispatched == [server.send_chat]


def test_a_command_is_dispatched_off_the_event_loop(monkeypatch):
    """Same guard for /commit, /init and the others that shell out."""
    dispatched: list[object] = []

    async def spy(func, /, *args, **kwargs):
        dispatched.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(server, "_run_blocking", spy)
    client = TestClient(server.create_app(token=TOKEN, allowed_origins={ORIGIN}))

    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as ws:
        ws.send_text(auth_frame())
        ws.receive_text()
        ws.send_text(
            json.dumps(
                {
                    "id": "c1",
                    "type": "request",
                    "method": "command.run",
                    "params": {"text": "/status"},
                }
            )
        )
        assert "Citrine status" in parse_envelope(ws.receive_text()).params["text"]

    assert dispatched == [server.run_command]


def test_the_ping_deadline_outlasts_a_long_turn():
    """uvicorn's 20s default pong deadline dropped the socket mid-turn.

    Keeping the event loop free is necessary but not sufficient: the client
    also has to be given long enough to answer.
    """
    import inspect

    source = inspect.getsource(server.main)
    assert "ws_ping_timeout" in source


# ------------------------------------------------------------ the turn budget


def clock(*ticks: float):
    """A monotonic clock that reads the given values in order, then holds."""
    readings = list(ticks)

    def read() -> float:
        return readings.pop(0) if len(readings) > 1 else readings[0]

    return read


def test_the_turn_stops_when_its_budget_is_spent(tmp_path, monkeypatch):
    """A tool-calling loop must not outlive the budget, round cap or not.

    The clock is driven rather than waited on: the deadline is taken at 0, the
    first round runs, and by the second round an hour has passed.
    """
    monkeypatch.setattr(chat.time, "monotonic", clock(0.0, 0.0, 3_600.0))
    script = [tool_response("git", {"args": ["status"]}) for _ in range(6)]
    with fake_provider(script) as fake:
        cfg = config_for(fake.base_url)
        cfg.tools.workspace_root = str(tmp_path)
        result = send_chat("go", cfg)

    assert "ran out of time" in result.text


def test_the_budget_stop_reports_the_tools_it_did_run(tmp_path, monkeypatch):
    """Otherwise the user has no idea what the turn managed to do."""
    monkeypatch.setattr(chat.time, "monotonic", clock(0.0, 0.0, 3_600.0))
    with fake_provider([tool_response("git", {"args": ["status"]})]) as fake:
        cfg = config_for(fake.base_url)
        cfg.tools.workspace_root = str(tmp_path)
        result = send_chat("go", cfg)

    assert "git" in result.text


def test_the_budget_message_names_the_knob_to_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(chat.time, "monotonic", clock(0.0, 0.0, 3_600.0))
    with fake_provider([tool_response("git", {"args": ["status"]})]) as fake:
        cfg = config_for(fake.base_url)
        cfg.tools.workspace_root = str(tmp_path)
        result = send_chat("go", cfg)

    assert "turn_budget_s" in result.text


def test_the_budget_never_cuts_a_turn_below_one_provider_call(tmp_path, monkeypatch):
    """A budget under one call timeout would fail every turn on arrival.

    Treating it as "at least one call" is the only reading that leaves the
    setting usable, so it is pinned here rather than left to chance.
    """
    seen: list[float] = []
    original = chat.urllib.request.urlopen

    def spy(request, timeout=None):
        seen.append(timeout)
        return original(request, timeout=timeout)

    monkeypatch.setattr(chat.urllib.request, "urlopen", spy)
    with fake_provider([text_response("ok")]) as fake:
        cfg = config_for(fake.base_url)
        cfg.tools.workspace_root = str(tmp_path)
        cfg.request_timeout_s = 60
        cfg.turn_budget_s = 5
        result = send_chat("go", cfg)

    assert result.text == "ok"
    assert seen == [60]


def test_an_ordinary_turn_is_untouched_by_the_budget(tmp_path):
    """The budget must not be a tax on turns that finish promptly."""
    with fake_provider([text_response("all good")]) as fake:
        cfg = config_for(fake.base_url)
        cfg.tools.workspace_root = str(tmp_path)
        result = send_chat("go", cfg)

    assert result.text == "all good"


def test_the_request_timeout_reaches_the_provider_call(tmp_path, monkeypatch):
    """The configured timeout has to be the one urllib is actually given."""
    seen: list[float] = []
    original = chat.urllib.request.urlopen

    def spy(request, timeout=None):
        seen.append(timeout)
        return original(request, timeout=timeout)

    monkeypatch.setattr(chat.urllib.request, "urlopen", spy)
    with fake_provider([text_response("ok")]) as fake:
        cfg = config_for(fake.base_url)
        cfg.tools.workspace_root = str(tmp_path)
        cfg.request_timeout_s = 45
        send_chat("go", cfg)

    assert seen == [45]


def test_an_absurdly_small_timeout_is_floored(tmp_path, monkeypatch):
    """A config of 1s would fail every call; treat it as a typo, not a rule."""
    seen: list[float] = []
    original = chat.urllib.request.urlopen

    def spy(request, timeout=None):
        seen.append(timeout)
        return original(request, timeout=timeout)

    monkeypatch.setattr(chat.urllib.request, "urlopen", spy)
    with fake_provider([text_response("ok")]) as fake:
        cfg = config_for(fake.base_url)
        cfg.tools.workspace_root = str(tmp_path)
        cfg.request_timeout_s = 1
        send_chat("go", cfg)

    assert seen == [30]


# ------------------------------------------------------- the timeout message


def test_a_read_timeout_is_reported_as_a_timeout_not_as_being_offline(
    tmp_path, monkeypatch
):
    """"network error: timed out" sent users to check their wifi."""

    def timing_out(request, timeout=None):
        raise chat.urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(chat.urllib.request, "urlopen", timing_out)
    cfg = config_for("http://127.0.0.1:1/v1")
    cfg.tools.workspace_root = str(tmp_path)
    result = send_chat("go", cfg)

    assert "did not respond within" in result.text
    assert "network error" not in result.text


def test_the_timeout_message_names_the_knob_to_turn(tmp_path, monkeypatch):
    def timing_out(request, timeout=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(chat.urllib.request, "urlopen", timing_out)
    cfg = config_for("http://127.0.0.1:1/v1")
    cfg.tools.workspace_root = str(tmp_path)
    result = send_chat("go", cfg)

    assert "request_timeout_s" in result.text


def test_a_real_network_failure_still_says_so(tmp_path, monkeypatch):
    def refused(request, timeout=None):
        raise chat.urllib.error.URLError("connection refused")

    monkeypatch.setattr(chat.urllib.request, "urlopen", refused)
    cfg = config_for("http://127.0.0.1:1/v1")
    cfg.tools.workspace_root = str(tmp_path)
    result = send_chat("go", cfg)

    assert "network error" in result.text
