"""Saved sessions: persistence across restarts, and deletion.

The store is exercised through real sqlite files in a scratch CITRINE_HOME
(conftest redirects it), including across separate HistoryStore instances -
because the point of persistence is that a *new* process sees what an old one
wrote, and a test that reuses one instance would never notice the store was
lying about that.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from citrine import history
from citrine.commands import run_command
from citrine.config import CitrineConfig
from citrine.history import MAX_MESSAGES, HistoryStore


@pytest.fixture()
def config() -> CitrineConfig:
    return CitrineConfig()


class TestPersistence:
    def test_turns_survive_a_new_store_instance(self, tmp_path):
        """The whole point: a reopened app sees yesterday's conversation."""
        first = HistoryStore(db_path=tmp_path / "sessions.sqlite3")
        first.record_turn("k", "what did we do?", "we read the file")

        second = HistoryStore(db_path=tmp_path / "sessions.sqlite3")

        messages = second.messages_for("k")
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[0]["content"] == "what did we do?"
        assert messages[1]["content"] == "we read the file"

    def test_conversations_are_isolated_by_key(self, tmp_path):
        store = HistoryStore(db_path=tmp_path / "db.sqlite3")
        store.record_turn("session-a", "q a", "a a")
        store.record_turn("session-b", "q b", "a b")

        assert [m["content"] for m in store.messages_for("session-a")] == ["q a", "a a"]
        assert [m["content"] for m in store.messages_for("session-b")] == ["q b", "a b"]

    def test_clear_removes_one_conversation_only(self, tmp_path):
        store = HistoryStore(db_path=tmp_path / "db.sqlite3")
        store.record_turn("keep", "q", "a")
        store.record_turn("drop", "q", "a")

        store.clear("drop")

        assert store.messages_for("keep")
        assert store.messages_for("drop") == []

    def test_trims_to_the_cap_in_whole_pairs(self, tmp_path):
        store = HistoryStore(db_path=tmp_path / "db.sqlite3")
        for index in range(MAX_MESSAGES // 2 + 10):
            store.record_turn("k", f"q{index}", f"a{index}")

        messages = store.messages_for("k")
        assert len(messages) == MAX_MESSAGES
        # Whole pairs, oldest dropped first.
        assert messages[0]["content"] == f"q{10}"
        assert messages[-1]["content"] == f"a{MAX_MESSAGES // 2 + 9}"

    def test_delete_prefix_removes_a_session_across_agents_and_epochs(self, tmp_path):
        """A prefix covers one agent's session across reset epochs - no more.

        Deleting a whole session is the caller's job (the /session delete
        command loops over agents); the store primitive stays precise.
        """
        store = HistoryStore(db_path=tmp_path / "db.sqlite3")
        store.record_turn("Coder::work#0", "q", "a")
        store.record_turn("Coder::work#1", "q", "a")  # after a /reset
        store.record_turn("Writer::work#0", "q", "a")  # another agent
        store.record_turn("Coder::other#0", "q", "a")  # another session

        removed = store.delete_prefix("Coder::work#")

        # Rows, not turns: each recorded turn is a user row and an assistant
        # row, so two conversations come out as four deleted rows.
        assert removed == 4
        assert store.messages_for("Coder::work#0") == []
        assert store.messages_for("Coder::work#1") == []
        assert len(store.messages_for("Writer::work#0")) == 2
        assert len(store.messages_for("Coder::other#0")) == 2


class TestSessionDelete:
    def test_delete_removes_the_session_from_the_switcher(self, config):
        run_command("/new", config)
        run_command("/session main", config)
        run_command("/session delete session-1", config)

        assert config.sessions == ["main"]

    def test_delete_refuses_the_active_session(self, config):
        run_command("/new", config)
        result = run_command("/session delete session-1", config)

        assert "active session" in result
        assert "session-1" in config.sessions

    def test_delete_refuses_an_unknown_session(self, config):
        result = run_command("/session delete ghost", config)
        assert "No such session" in result

    def test_delete_clears_token_buckets_and_history(self, config):
        from citrine import history
        from citrine.config import usage_key

        run_command("/new", config)
        run_command("/agent Coder", config)
        config.add_session_tokens(500)  # Coder in session-1
        history.STORE.record_turn(config.transcript_key(), "q", "a")

        run_command("/session main", config)
        history.STORE.record_turn(config.transcript_key(), "keep me", "kept")
        result = run_command("/session delete session-1", config)

        assert "deleted" in result
        assert "session-1" not in config.sessions
        assert usage_key("Coder", "session-1") not in config.token_usage
        # History for that session is gone for the agent it belonged to...
        assert history.STORE.messages_for("Coder::session-1#0") == []
        # ...and the untouched session is not.
        assert history.STORE.messages_for(config.transcript_key())


class TestResetClearsMemory:
    def test_reset_forgets_the_conversation(self, config):
        from citrine import history

        key = config.transcript_key()
        history.STORE.record_turn(key, "secret plan", "i remember it")

        run_command("/reset", config)

        # The epoch moved, so the new key is fresh - and the old one is empty.
        assert config.transcript_key() != key
        assert history.STORE.messages_for(key) == []


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A scratch CITRINE_HOME (conftest also sets this; tests that need the
    path itself use this fixture)."""
    path = tmp_path / "home"
    monkeypatch.setenv("CITRINE_HOME", str(path))
    return path


class TestHistoryMethod:
    def test_history_get_returns_the_saved_conversation(self, home):
        from citrine.server import create_app

        # The server reads config from CITRINE_HOME; write a minimal one.
        home.mkdir(parents=True, exist_ok=True)
        (home / "config.json").write_text("{}", encoding="utf-8")

        key = "Default::main#0"
        HistoryStore().record_turn(key, "earlier question", "earlier answer")

        app = create_app(token="tok", allowed_origins=set())
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_text(json.dumps(
                    {"id": "a1", "type": "request", "method": "auth", "params": {"token": "tok"}}
                ))
                ws.receive_text()
                ws.send_text(json.dumps(
                    {"id": "h1", "type": "request", "method": "history.get", "params": {}}
                ))
                reply = json.loads(ws.receive_text())

        assert reply["method"] == "history.get"
        assert reply["params"]["key"] == key
        assert reply["params"]["messages"] == [
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
        ]
