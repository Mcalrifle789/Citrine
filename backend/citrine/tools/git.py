"""Git, as a tool.

The tool is a thin, honest wrapper over the ``git`` executable rather than a
reimplementation: the user's git config, hooks, credential helper, and aliases
all apply, which is what makes it feel like *their* git.

Two things are added on top of a plain passthrough:

* the destructive subcommands (``reset --hard``, ``clean -fdx``, forced pushes)
  are routed through the same guard the terminal tool uses, so opting into
  destructive commands is one decision, not two;
* ``commit`` carries the ``Co-Authored-By:`` trailer that credits Citrine, so
  an agent-made commit is attributable in the history - the same mechanism
  ``github.py`` uses for repositories it creates.
"""

from __future__ import annotations

import shlex
import subprocess

from citrine.git_identity import add_coauthor_trailer, citrine_identity
from citrine.tools.base import ToolContext, ToolResult, truncate
from citrine.tools.terminal import blocked_reason

GIT_TIMEOUT_S = 120
MAX_CAPTURED_CHARS = 400_000


def _split(args) -> list[str]:
    """Accept either a list of arguments or a single command string."""
    if isinstance(args, str):
        return shlex.split(args)
    if isinstance(args, (list, tuple)):
        return [str(item) for item in args]
    return []


def run_git(args, ctx: ToolContext, *, cwd: str | None = None, credit: bool = True) -> ToolResult:
    """Run a git command in the workspace and return its output."""
    if not ctx.allow_git:
        return ToolResult.failure("git access is disabled (tools.allow_git is false)")

    argv = _split(args)
    if not argv:
        return ToolResult.failure("No git arguments given. Example: ['status', '--short']")

    blocked = blocked_reason("git " + " ".join(argv))
    if blocked and not ctx.allow_destructive:
        return ToolResult.failure(
            f"Refused: `git {' '.join(argv)}` looks like {blocked}. Set "
            "tools.allow_destructive to true (or /tools destructive on) if you "
            "really mean it."
        )

    working_dir = ctx.resolve(cwd, default=".")

    if credit and argv[0] == "commit":
        argv = _credit_commit(argv)

    try:
        completed = subprocess.run(  # noqa: S603 - arguments are passed as a list
            ["git", *argv],
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=GIT_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return ToolResult.failure(
            "git is not installed or not on PATH. Install git, or use run_command "
            "to see what is available."
        )
    except subprocess.TimeoutExpired:
        return ToolResult.failure(f"git {' '.join(argv)} timed out after {GIT_TIMEOUT_S}s.")
    except OSError as exc:
        return ToolResult.failure(f"Could not run git: {exc}")

    parts = [f"$ git {' '.join(argv)}", f"[cwd: {working_dir}]", f"[exit code: {completed.returncode}]"]
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr] {stderr}")
    if not stdout and not stderr:
        parts.append("[no output]")

    body = truncate("\n".join(parts), MAX_CAPTURED_CHARS, note="git output truncated")
    return ToolResult.success(truncate(body, ctx.max_output_chars, note="git output truncated"))


def _has_author(argv: list[str]) -> bool:
    return any(argument.startswith("--author") for argument in argv)


def _credit_commit(argv: list[str]) -> list[str]:
    """Add Citrine's co-author trailer to a commit's message.

    Three cases have to be handled, and the first two are why this is not a
    one-liner:

    * a message that already credits Citrine is left alone (amending must not
      stack trailers);
    * ``-m`` can appear more than once, and git joins those paragraphs - so the
      trailer goes on the *last* one, and the check looks at *all* of them;
      appending to each would produce two identical trailers in one commit;
    * an explicit ``--author`` is a deliberate choice by the caller, so the
      co-author trailer is skipped rather than fighting it.
    """
    if _has_author(argv):
        return argv

    indexes = _message_indexes(argv)
    if not indexes:
        return argv

    if _already_credits([argv[index] for index in indexes]):
        return argv

    last = indexes[-1]
    argv[last] = add_coauthor_trailer(argv[last], citrine_identity())
    return argv


def _already_credits(messages: list[str]) -> bool:
    return any("co-authored-by:" in message.lower() for message in messages)


def _message_indexes(argv: list[str]) -> list[int]:
    """Indexes of the arguments holding commit-message text."""
    indexes: list[int] = []
    for index, argument in enumerate(argv):
        if argument in {"-m", "--message"} and index + 1 < len(argv):
            indexes.append(index + 1)
        elif argument.startswith("--message="):
            indexes.append(index)
    return indexes
