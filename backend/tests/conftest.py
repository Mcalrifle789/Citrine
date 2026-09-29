"""Shared fixtures for the backend suite.

The conversation history store is process-global on purpose - it is the
agent's memory for the life of the backend. That is exactly why every test
needs a fresh one: without this, two tests that happen to use the same
transcript key leak turns into each other, and assertions on message indexes
start depending on test order.
"""

from __future__ import annotations

import pytest

from citrine import history


@pytest.fixture(autouse=True)
def fresh_history(monkeypatch):
    monkeypatch.setattr(history, "STORE", history.HistoryStore())
