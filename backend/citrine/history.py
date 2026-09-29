"""What the agent remembers between messages.

The first cut of the tool loop had a defect that looked like a model defect:
every turn started from a blank context, so an agent that had just read five
files would read the same five files again on the next message. The transcript
showed it as `read_file, read_file, read_file...` - tool spam with no progress.
The tools worked; nothing they learned survived the turn.

This store is that fix, and its shape follows from three constraints:

* **Keyed by the transcript key** (agent + session + epoch), so `/new`,
  `/session`, `/agent` and `/reset` - which already move that key for the
  renderer's benefit - discard the model's memory at exactly the moment the
  window goes blank. One key, two meanings, no drift between what the user
  sees and what the model knows.
* **In memory, not on disk.** Sessions live in a sqlite file in a later slice;
  until then an app restart starting a fresh conversation is honest, whereas a
  half-designed persistence layer silently disagreeing with the renderer's
  scrollback is not.
* **It stores conclusions, not payloads.** Attachment-folded prompts and tool
  results are turn-local. Persisting a 64 KB file dump into every future turn
  would buy memory at the price of the context window, and the assistant's own
  summary is worth more to the next turn than the raw text it read.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# How many user/assistant pairs are kept per conversation. Forty pairs of
# typical messages is far past what most providers accept; the cap exists so a
# long session degrades by forgetting its oldest turns instead of failing.
MAX_MESSAGES = 80


@dataclass
class HistoryStore:
    """Thread-safe, in-memory conversation memory."""

    # The backend serves requests from a thread pool (asyncio.to_thread), so
    # two turns for the same conversation can interleave.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    conversations: dict[str, list[dict]] = field(default_factory=dict)

    def messages_for(self, key: str) -> list[dict]:
        """A copy of the stored turns for a conversation, oldest first."""
        with self.lock:
            return [dict(message) for message in self.conversations.get(key, [])]

    def record_turn(self, key: str, user_text: str, assistant_text: str) -> None:
        """Append one completed exchange, then trim to the cap.

        Only completed turns are recorded: a turn that failed mid-flight leaves
        no memory, so retrying it starts clean instead of building on a
        half-finished context.
        """
        with self.lock:
            conversation = self.conversations.setdefault(key, [])
            conversation.append({"role": "user", "content": user_text})
            conversation.append({"role": "assistant", "content": assistant_text})
            if len(conversation) > MAX_MESSAGES:
                # Drop from the front in pairs, so the list never begins with
                # an assistant reply that has lost its question.
                excess = len(conversation) - MAX_MESSAGES
                del conversation[: excess + excess % 2]

    def clear(self, key: str) -> None:
        with self.lock:
            self.conversations.pop(key, None)


# One store for the life of the backend process.
STORE = HistoryStore()
