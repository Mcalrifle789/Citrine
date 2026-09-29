"""Running commands: the terminal, as a tool.

This is the sharpest tool in the set, so the guards are worth stating plainly:

* A **denylist** of commands that destroy a machine or a repository without
  asking. Matching is deliberately blunt (substring, on the raw command) -
  a clever matcher the user cannot predict is worse than an obvious one, and
  the failure mode of a false positive is a clear refusal message, not damage.
  ``tools.allow_destructive`` exists for the user who genuinely wants them.
* A **timeout**, because a command that waits on stdin or loops forever would
  otherwise hold the conversation open indefinitely.
* An **output cap**, so a runaway build log cannot push the user's actual
  question out of the context window.

There is no sandbox. The command runs as the user, in the workspace root, and
the documentation says so rather than implying a boundary that is not there.
"""

from __future__ import annotations

import subprocess
import sys

from citrine.tools.base import ToolContext, ToolResult, truncate, format_bytes

MAX_CAPTURED_CHARS = 400_000

# Substring patterns, lowercased and matched against the raw command. These are
# the accidents worth preventing, not an exhaustive security boundary.
DESTRUCTIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("rm -rf /", "recursive delete of the filesystem root"),
    ("rm -rf /*", "recursive delete of the filesystem root"),
    ("rm -fr /", "recursive delete of the filesystem root"),
    ("del /f /s /q c:", "recursive delete of the C: drive"),
    ("rd /s /q c:", "recursive delete of the C: drive"),
    ("rmdir /s /q c:", "recursive delete of the C: drive"),
    ("format c:", "formatting a system drive"),
    ("mkfs", "formatting a filesystem"),
    ("diskpart", "partition table editing"),
    ("shutdown", "shutting down the machine"),
    ("logout", "logging the user out"),
    ("git clean -xfd", "deleting untracked files"),
    ("git clean -fdx", "deleting untracked files"),
    ("git reset --hard", "discarding uncommitted work"),
    ("git push --force", "rewriting published history"),
    ("git push -f ", "rewriting published history"),
    (":(){", "fork bomb"),
    ("reg delete hklm", "deleting machine-wide registry keys"),
    ("cipher /w", "overwriting free space"),
    ("vssadmin delete", "deleting shadow copies"),
    ("bcdedit", "editing the boot configuration"),
)


def blocked_reason(command: str) -> str | None:
    """Return why a command is blocked, or None when it is allowed."""
    lowered = command.lower()
    for pattern, reason in DESTRUCTIVE_PATTERNS:
        if pattern in lowered:
            return reason
    return None


def run_command(
    command: str,
    ctx: ToolContext,
    *,
    cwd: str | None = None,
    timeout_s: int | None = None,
) -> ToolResult:
    """Run a shell command in the workspace and capture its output."""
    if not ctx.allow_terminal:
        return ToolResult.failure("terminal access is disabled (tools.allow_terminal is false)")

    text = (command or "").strip()
    if not text:
        return ToolResult.failure("No command given.")

    reason = blocked_reason(text)
    if reason and not ctx.allow_destructive:
        return ToolResult.failure(
            f"Refused: this command looks like {reason}, which is on the "
            "destructive list. Set tools.allow_destructive to true (or "
            "/tools destructive on) if you really mean it."
        )

    working_dir = ctx.resolve(cwd, default=".")
    if not working_dir.exists():
        return ToolResult.failure(f"Working directory does not exist: {working_dir}")

    timeout = max(1, timeout_s or ctx.timeout_s)
    try:
        completed = subprocess.run(  # noqa: S602 - shell use is the feature
            text,
            shell=True,
            cwd=str(working_dir),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return ToolResult.failure(
            f"Command timed out after {timeout}s and was stopped: {text}"
        )
    except OSError as exc:
        return ToolResult.failure(f"Could not run the command: {exc}")

    return ToolResult.success(_format(completed, text, working_dir, ctx))


def _format(
    completed: subprocess.CompletedProcess[str],
    command: str,
    working_dir,
    ctx: ToolContext,
) -> str:
    parts = [f"$ {command}", f"[cwd: {working_dir}]", f"[exit code: {completed.returncode}]"]
    stdout = truncate(completed.stdout or "", MAX_CAPTURED_CHARS, note="stdout truncated")
    stderr = truncate(completed.stderr or "", MAX_CAPTURED_CHARS, note="stderr truncated")
    if stdout.strip():
        parts.append(f"[stdout]\n{stdout.rstrip()}")
    if stderr.strip():
        parts.append(f"[stderr]\n{stderr.rstrip()}")
    if not stdout.strip() and not stderr.strip():
        parts.append("[no output]")

    body = "\n".join(parts)
    # The per-command cap is the one that matters for the chat turn; the
    # capture cap above only stops pathological buffers reaching memory.
    return truncate(body, ctx.max_output_chars, note="command output truncated")


def shell_description() -> str:
    """A one-line description of the shell commands will run in."""
    if sys.platform == "win32":
        return "cmd.exe (Windows)"
    return "/bin/sh"
