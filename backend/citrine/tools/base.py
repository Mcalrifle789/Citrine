"""Shared plumbing for the agent's tools.

Every tool receives a :class:`ToolContext` and returns a :class:`ToolResult`.
The context carries the policy the user configured, so a tool never has to
reach into the config itself - which keeps the policy in one place and makes
every tool testable with a plain object instead of a config file on disk.

Failures are returned as results, not raised. A tool that raises takes down
the whole chat turn; a tool that returns "I refused, here is why" lets the
model read the reason and either adapt or tell the user. That distinction
matters most for the guards: *"this command is on the destructive list"* is far
more useful to the model than an exception it cannot see.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ToolError(RuntimeError):
    """A tool could not complete the request as asked."""


@dataclass(frozen=True)
class ToolResult:
    """The outcome of one tool call, as the model will see it."""

    ok: bool
    content: str

    @classmethod
    def success(cls, content: str) -> "ToolResult":
        return cls(True, content)

    @classmethod
    def failure(cls, content: str) -> "ToolResult":
        return cls(False, content)


@dataclass
class ToolContext:
    """Where tools run and what they are allowed to do."""

    root: Path
    allow_files: bool = True
    allow_write: bool = True
    allow_terminal: bool = True
    allow_git: bool = True
    allow_network: bool = True
    allow_destructive: bool = False
    allow_outside_workspace: bool = True
    timeout_s: int = 60
    max_output_chars: int = 20_000
    max_file_bytes: int = 200_000

    def resolve(self, raw: str | None, *, default: str = ".") -> Path:
        """Resolve a user-supplied path against the workspace root.

        Relative paths are joined to the root rather than the process working
        directory, so a tool call behaves the same no matter where the backend
        was launched from. Absolute paths anywhere on the machine are allowed
        by default; the workspace is where relative paths land and where
        commands run, not a jail.
        """
        text = (raw or default).strip() or default
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            resolved = candidate.resolve()
        except OSError as exc:  # pragma: no cover - platform specific
            raise ToolError(f"cannot resolve path {text!r}: {exc}") from exc

        if self.allow_outside_workspace:
            return resolved
        if resolved != self.root and not resolved.is_relative_to(self.root):
            raise ToolError(
                f"{resolved} is outside the workspace root {self.root}. "
                "Set tools.allow_outside_workspace to true, or change the root "
                "with /workspace <path>."
            )
        return resolved


def truncate(text: str, limit: int, *, note: str = "output truncated") -> str:
    """Cap a tool result, saying so rather than silently dropping the tail."""
    if limit <= 0 or len(text) <= limit:
        return text
    return f"{text[:limit]}\n... [{note}: {len(text) - limit} more characters]"


def format_bytes(count: int) -> str:
    if count < 1024:
        return f"{count} B"
    if count < 1024 * 1024:
        return f"{count / 1024:.1f} KB"
    return f"{count / (1024 * 1024):.1f} MB"
