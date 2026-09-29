"""What the agent remembers between messages.

The first cut of the tool loop had a defect that looked like a model defect:
every turn started from a blank context, so an agent that had just read five
files would read the same five files again on the next message. The transcript
showed it as `read_file, read_file, read_file...` - tool spam with no progress.
The tools worked; nothing they learned survived the turn.

Turns are persisted in `~/.citrine/sessions.sqlite3`, so memory now survives an
app restart: the agent walks back into a conversation knowing what it did
yesterday, not just what it did five minutes ago. The store is keyed by the
transcript key (agent + session + epoch), which is the same key the renderer
files its scrollback under - so `/new`, `/session`, `/agent` and `/reset`
discard the model's memory at exactly the moment the window goes blank. One
key, two meanings, no drift between what the user sees and what the model
knows.

What is stored is deliberately narrow: what was asked and what was concluded.
Attachment-folded prompts and tool results are turn-local. Persisting a 64 KB
file dump into every future turn would buy memory at the price of the context
window, and the assistant's own summary is worth more to the next turn than
the raw text it read.

Deleting is a first-class operation, not an afterthought: sessions are the
user's data, and `delete_prefix` exists so removing a session removes its
conversation everywhere it lives - every agent, every reset epoch.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from citrine.paths import ensure_dirs, sessions_db_path

# How many user/assistant pairs are kept per conversation. Forty pairs of
# typical messages is far past what most providers accept; the cap exists so a
# long session degrades by forgetting its oldest turns instead of failing.
MAX_MESSAGES = 80

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_key TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_turns_key ON turns(transcript_key, id);
"""


class HistoryStore:
    """Persistent conversation memory, keyed by transcript key.

    The backend serves requests from a thread pool (asyncio.to_thread), so a
    connection is opened per operation rather than shared across threads.
    For a local app writing a few rows per exchange, that cost is nothing
    next to the model call that preceded it.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or sessions_db_path()
        self._lock = threading.Lock()
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialise(self) -> None:
        ensure_dirs()
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def messages_for(self, key: str) -> list[dict]:
        """The stored turns for a conversation, oldest first."""
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT role, content FROM turns WHERE transcript_key = ? ORDER BY id",
                (key,),
            ).fetchall()
        return [{"role": role, "content": content} for role, content in rows]

    def record_turn(self, key: str, user_text: str, assistant_text: str) -> None:
        """Append one completed exchange, then trim to the cap.

        Only completed turns are recorded: a turn that failed mid-flight leaves
        no memory, so retrying it starts clean instead of building on a
        half-finished context.
        """
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO turns (transcript_key, role, content) VALUES (?, ?, ?)",
                (key, "user", user_text),
            )
            connection.execute(
                "INSERT INTO turns (transcript_key, role, content) VALUES (?, ?, ?)",
                (key, "assistant", assistant_text),
            )
            # Trim from the front in pairs, so the conversation never begins
            # with an assistant reply that has lost its question.
            excess = self._count(connection, key) - MAX_MESSAGES
            if excess > 0:
                connection.execute(
                    """
                    DELETE FROM turns WHERE id IN (
                        SELECT id FROM turns WHERE transcript_key = ?
                        ORDER BY id LIMIT ?
                    )
                    """,
                    (key, excess + excess % 2),
                )

    def clear(self, key: str) -> None:
        """Forget one conversation entirely."""
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM turns WHERE transcript_key = ?", (key,))

    def delete_prefix(self, prefix: str) -> int:
        """Forget every conversation whose key starts with ``prefix``.

        This is how a session dies properly: its transcript key embeds the
        session name, so a prefix covers the session across every agent and
        every reset epoch. Returns how many turns were removed.
        """
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM turns WHERE transcript_key LIKE ?",
                (prefix + "%",),
            )
            return cursor.rowcount

    @staticmethod
    def _count(connection: sqlite3.Connection, key: str) -> int:
        row = connection.execute(
            "SELECT COUNT(*) FROM turns WHERE transcript_key = ?", (key,)
        ).fetchone()
        return int(row[0]) if row else 0


# One store for the life of the backend process.
STORE = HistoryStore()
