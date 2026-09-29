"""Shared fixtures for the backend suite.

Two pieces of global state must be reset per test:

* The conversation history store is process-global on purpose - it is the
  agent's memory for the life of the backend. Tests get a fresh one, because
  two tests that happen to use the same transcript key would otherwise leak
  turns into each other and make assertions depend on test order.
* CITRINE_HOME points at a scratch directory, so a test can never read the
  user's real config or write turns into their real session database.
"""

from __future__ import annotations

import pytest

from citrine import history


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path / "home"))


@pytest.fixture(autouse=True)
def fresh_history(monkeypatch, isolated_home):
    """A new store per test, constructed after CITRINE_HOME is redirected."""
    monkeypatch.setattr(history, "STORE", history.HistoryStore())
