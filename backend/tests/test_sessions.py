"""Sessions, agents, and the token counts that hang off them.

Three separate complaints motivated this file, and they are all the same bug
wearing different hats:

* ``/new`` left the previous conversation on screen, so a "new session" looked
  like a continuation of the old one.
* Token usage was keyed by session alone, so switching agents - which switches
  model, and therefore context window - carried the old agent's count across.
* Nothing reset a count without also renaming the session.

The fix is a single identity for "which conversation is this": agent, session,
and a reset epoch. ``transcript_key()`` is that identity, the renderer keys its
scrollback on it, and ``usage_key()`` is the same identity without the epoch.
"""

import json

import pytest
from fastapi.testclient import TestClient

from citrine.app_status import app_status
from citrine.commands import run_command
from citrine.config import AgentConfig, CitrineConfig, ProviderConfig, usage_key
from citrine.protocol import parse_envelope
from citrine.server import create_app


@pytest.fixture
def config() -> CitrineConfig:
    return CitrineConfig(
        providers=[ProviderConfig(id="custom", label="OpenRouter", model="gpt-4o-mini")],
        active_provider_id="custom",
    )


# --------------------------------------------------------------------- /new


def test_new_session_becomes_the_active_one(config):
    run_command("/new", config)
    assert config.active_session == "session-1"


def test_new_session_does_not_reuse_a_name(config):
    """A reused name would re-open the old transcript instead of a blank one."""
    run_command("/new", config)
    run_command("/new", config)
    assert config.sessions == ["main", "session-1", "session-2"]


def test_new_session_changes_the_transcript_key(config):
    """This is what blanks the window: a different key is a different window."""
    before = config.transcript_key()
    run_command("/new", config)
    assert config.transcript_key() != before


def test_new_session_starts_at_zero_tokens(config):
    config.add_session_tokens(5_000)
    run_command("/new", config)
    assert config.session_tokens() == 0


def test_new_session_does_not_spend_the_old_session_count(config):
    """The old count still has to be there when the user goes back to it."""
    config.add_session_tokens(5_000)
    run_command("/new", config)
    config.active_session = "main"
    assert config.session_tokens() == 5_000


def test_new_session_names_the_agent_and_model_it_starts_with(config):
    config.active_agent_config().model = "gpt-4o-mini"
    output = run_command("/new", config)
    assert "gpt-4o-mini" in output
    assert "0" in output


# ----------------------------------------------------------------- /session


def test_switching_session_changes_the_transcript_key(config):
    run_command("/session work", config)
    assert "work" in config.transcript_key()


def test_a_brand_new_session_name_starts_at_zero(config):
    config.add_session_tokens(900)
    run_command("/session work", config)
    assert config.session_tokens() == 0


def test_returning_to_a_session_restores_its_count(config):
    config.add_session_tokens(900)
    run_command("/session work", config)
    config.add_session_tokens(10)
    run_command("/session main", config)
    assert config.session_tokens() == 900


def test_switching_to_the_current_session_is_a_no_op(config):
    """Otherwise re-selecting the active session would zero its count."""
    config.add_session_tokens(900)
    output = run_command("/session main", config)
    assert "Already on session main" in output
    assert config.session_tokens() == 900


def test_session_switch_reports_the_count_of_the_session_it_moved_to(config):
    config.add_session_tokens(900)
    run_command("/session work", config)
    output = run_command("/session main", config)
    assert "900" in output


# ------------------------------------------------------------------- /agent


def test_token_usage_is_per_agent_not_just_per_session(config):
    """The complaint: switching agent kept the previous agent's token count.

    An agent switch usually switches model, and a count measured against a
    different context window is not the same number.
    """
    config.agents.append(AgentConfig(name="Scout", model="gpt-4o"))
    config.add_session_tokens(7_000)
    run_command("/agent Scout", config)
    assert config.session_tokens() == 0


def test_switching_back_restores_that_agents_count(config):
    config.agents.append(AgentConfig(name="Scout", model="gpt-4o"))
    config.add_session_tokens(7_000)
    run_command("/agent Scout", config)
    config.add_session_tokens(12)
    run_command("/agent Default", config)
    assert config.session_tokens() == 7_000


def test_agent_switch_changes_the_transcript_key(config):
    """Same session, different agent, different conversation."""
    config.agents.append(AgentConfig(name="Scout", model="gpt-4o"))
    before = config.transcript_key()
    run_command("/agent Scout", config)
    assert config.transcript_key() != before


def test_agent_switch_reports_the_model_it_switched_to(config):
    config.agents.append(AgentConfig(name="Scout", model="gpt-4o"))
    assert "gpt-4o" in run_command("/agent Scout", config)


def test_switching_to_the_current_agent_is_a_no_op(config):
    config.add_session_tokens(500)
    output = run_command("/agent Default", config)
    assert "Already on agent Default" in output
    assert config.session_tokens() == 500


def test_a_new_agent_starts_at_zero_tokens(config):
    config.add_session_tokens(7_000)
    run_command("/agent Scout", config)
    assert config.session_tokens() == 0


def test_choosing_a_model_does_not_change_another_agents_model(config):
    """/model is per agent, so it must not write through to the provider.

    The provider's model is the fallback for every agent that has not picked
    one; writing the choice there moved all of them at once.
    """
    config.agents.append(AgentConfig(name="Scout"))
    run_command("/model gpt-5", config)
    config.active_agent = "Scout"
    assert config.active_agent_config().model != "gpt-5"


def test_choosing_a_model_moves_the_active_agent(config):
    run_command("/model gpt-5", config)
    assert config.active_agent_config().model == "gpt-5"


# ------------------------------------------------------------------- /reset


def test_reset_keeps_the_session_name(config):
    run_command("/reset", config)
    assert config.active_session == "main"


def test_reset_still_changes_the_transcript_key(config):
    """The name has not changed, so only the epoch can signal the clear."""
    before = config.transcript_key()
    run_command("/reset", config)
    assert config.transcript_key() != before


def test_reset_zeroes_the_token_count(config):
    config.add_session_tokens(4_321)
    run_command("/reset", config)
    assert config.session_tokens() == 0


def test_reset_says_what_it_did(config):
    assert "reset" in run_command("/reset", config).lower()


# ------------------------------------------------------------ status payload


def test_app_status_carries_the_transcript_key(config):
    assert app_status(config)["transcript_key"] == config.transcript_key()


def test_app_status_reports_the_active_agents_tokens(config):
    config.agents.append(AgentConfig(name="Scout", model="gpt-4o"))
    config.add_session_tokens(2_000)
    config.active_agent = "Scout"
    assert app_status(config)["token_used"] == 0


def test_app_status_token_readout_follows_the_agent(config):
    config.active_agent_config().model = "gpt-4o"
    config.add_session_tokens(64_000)
    assert app_status(config)["tokens"] == "64k/128k"


# -------------------------------------------------------------- persistence


def test_usage_survives_a_round_trip(config):
    config.add_session_tokens(1_234)
    restored = CitrineConfig.from_dict(config.to_dict())
    assert restored.session_tokens() == 1_234


def test_the_epoch_survives_a_round_trip(config):
    run_command("/reset", config)
    restored = CitrineConfig.from_dict(config.to_dict())
    assert restored.transcript_key() == config.transcript_key()


def test_a_pre_agent_config_keeps_its_counts():
    """Older builds keyed usage by session name alone.

    Dropping those keys would silently zero the user's usage on upgrade, so
    they are attributed to the agent that was active when the file was written.
    """
    restored = CitrineConfig.from_dict(
        {
            "active_agent": "Default",
            "active_session": "main",
            "token_usage": {"main": 800},
        }
    )
    assert restored.token_usage == {usage_key("Default", "main"): 800}
    assert restored.session_tokens() == 800


def test_a_garbled_usage_entry_is_dropped_rather_than_raising():
    assert CitrineConfig.from_dict({"token_usage": {"main": "lots"}}).token_usage == {}


@pytest.mark.parametrize("stored", [None, [], "nope", 7])
def test_a_garbled_usage_block_falls_back_to_empty(stored):
    assert CitrineConfig.from_dict({"token_usage": stored}).token_usage == {}


@pytest.mark.parametrize(
    "field, default",
    [("transcript_epoch", 0), ("request_timeout_s", 180), ("turn_budget_s", 600)],
)
def test_timing_fields_fall_back_when_stored_garbled(field, default):
    assert getattr(CitrineConfig.from_dict({field: "soon"}), field) == default


# ---------------------------------------------------------- over the wire

TOKEN = "test-token-0123456789"
ORIGIN = "http://localhost:5173"


@pytest.fixture
def stored_config(tmp_path, monkeypatch):
    """Point load_config/save_config at a scratch file for the server tests."""
    monkeypatch.setattr("citrine.config.config_path", lambda: tmp_path / "config.json")
    return tmp_path / "config.json"


@pytest.fixture
def ws(stored_config):
    """An authenticated connection to a real backend app."""
    client = TestClient(create_app(token=TOKEN, allowed_origins={ORIGIN}))
    with client.websocket_connect("/ws", headers={"origin": ORIGIN}) as socket:
        socket.send_text(
            json.dumps(
                {"id": "a", "type": "request", "method": "auth", "params": {"token": TOKEN}}
            )
        )
        socket.receive_text()
        yield socket


def call(socket, method: str, params: dict | None = None) -> dict:
    socket.send_text(
        json.dumps({"id": "r", "type": "request", "method": method, "params": params or {}})
    )
    return parse_envelope(socket.receive_text()).params


def test_a_local_command_does_not_spend_context(ws):
    """A slash command runs against config and never reaches the model.

    Charging it an estimated cost was what made ``/new`` and ``/reset`` report
    a non-zero count for a conversation with nothing in it.
    """
    call(ws, "command.run", {"text": "/status"})
    assert call(ws, "app.status")["token_used"] == 0


def test_a_chat_turn_does_spend_context(ws):
    """The counter still has to move for the thing that actually costs."""
    call(ws, "chat.send", {"text": "hello"})
    assert call(ws, "app.status")["token_used"] > 0


def test_new_leaves_the_session_at_zero_over_the_wire(ws):
    """The end-to-end version of the complaint."""
    call(ws, "chat.send", {"text": "hello"})
    assert call(ws, "app.status")["token_used"] > 0

    call(ws, "command.run", {"text": "/new"})
    assert call(ws, "app.status")["token_used"] == 0


def test_new_moves_the_transcript_key_over_the_wire(ws):
    before = call(ws, "app.status")["transcript_key"]
    call(ws, "command.run", {"text": "/new"})
    assert call(ws, "app.status")["transcript_key"] != before


def test_reset_leaves_the_session_at_zero_over_the_wire(ws):
    """``/reset`` keeps the bucket, so nothing may be charged to it after."""
    call(ws, "chat.send", {"text": "hello"})
    call(ws, "command.run", {"text": "/reset"})
    assert call(ws, "app.status")["token_used"] == 0


def test_reset_moves_the_transcript_key_over_the_wire(ws):
    before = call(ws, "app.status")["transcript_key"]
    call(ws, "command.run", {"text": "/reset"})
    assert call(ws, "app.status")["transcript_key"] != before


def test_switching_agent_moves_the_transcript_key_over_the_wire(ws):
    before = call(ws, "app.status")["transcript_key"]
    call(ws, "command.run", {"text": "/agent Scout"})
    status = call(ws, "app.status")
    assert status["agent"] == "Scout"
    assert status["transcript_key"] != before


def test_switching_agent_leaves_the_new_agent_at_zero_over_the_wire(ws):
    call(ws, "chat.send", {"text": "hello"})
    call(ws, "command.run", {"text": "/agent Scout"})
    assert call(ws, "app.status")["token_used"] == 0


def test_the_previous_agent_count_is_still_there_on_the_way_back(ws):
    call(ws, "chat.send", {"text": "hello"})
    spent = call(ws, "app.status")["token_used"]
    call(ws, "command.run", {"text": "/agent Scout"})
    call(ws, "command.run", {"text": "/agent Default"})
    assert call(ws, "app.status")["token_used"] == spent
