"""File tools: read, write, list.

Reading is where binary files stop being a dead end. A file that decodes as
text is returned as text with line numbers; anything else is described through
citrine.tools.magic, which extracts what can be extracted and hands over a
base64 prefix, so "Citrine cannot read binary files" is no longer the answer.

Writes are atomic-ish (write to a temp file in the same directory, then
replace) so a crash mid-write cannot leave a half-written source file where a
working one used to be.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from citrine.tools.base import ToolContext, ToolError, ToolResult, format_bytes, truncate
from citrine.tools import magic

# How many lines of a text file are returned when the caller does not say.
DEFAULT_TEXT_LINES = 400


def _require_files(ctx: ToolContext) -> None:
    if not ctx.allow_files:
        raise ToolError("file access is disabled (tools.allow_files is false)")


def read_file(
    path: str,
    ctx: ToolContext,
    *,
    start_line: int = 1,
    max_lines: int = DEFAULT_TEXT_LINES,
    as_: str = "auto",
) -> ToolResult:
    """Read a file, decoding text or describing binary content."""
    _require_files(ctx)
    target = ctx.resolve(path)

    if not target.exists():
        return ToolResult.failure(f"No such file: {target}")
    if target.is_dir():
        return ToolResult.failure(
            f"{target} is a directory. Use list_dir to enumerate it."
        )

    try:
        size = target.stat().st_size
        with target.open("rb") as handle:
            # Always read a bounded amount: the point of the cap is that a
            # multi-gigabyte file cannot arrive in the context window.
            data = handle.read(max(ctx.max_file_bytes, 1))
        truncated_read = size > len(data)
    except OSError as exc:
        return ToolResult.failure(f"Could not read {target}: {exc}")

    if as_ == "base64":
        return ToolResult.success(magic.describe_binary(data))

    text = magic.decode_text(data) if as_ != "base64" else None

    if text is None:
        # Binary. Describing it is the whole point of this branch: the model
        # gets the type, any extractable text, and a base64 prefix it can work
        # with, instead of a refusal.
        body = magic.describe_binary(data)
        if truncated_read:
            body += (
                f"\n\n[note: only the first {format_bytes(len(data))} of "
                f"{format_bytes(size)} were read]"
            )
        return ToolResult.success(f"{target}\n{body}")

    lines = text.splitlines()
    start = max(1, start_line) - 1
    window = lines[start : start + max(1, max_lines)]
    numbered = "\n".join(
        f"{index + start + 1}\t{line}" for index, line in enumerate(window)
    )
    header = f"{target} ({format_bytes(size)}, {len(lines)} lines)"
    notes: list[str] = []
    if start > 0:
        notes.append(f"started at line {start + 1}")
    if start + len(window) < len(lines):
        notes.append(
            f"{len(lines) - (start + len(window))} more lines; "
            "call read_file again with start_line to continue"
        )
    if truncated_read:
        notes.append(f"only the first {format_bytes(len(data))} were read")
    suffix = f"\n[{'; '.join(notes)}]" if notes else ""
    body = truncate(numbered, ctx.max_output_chars, note="file text truncated")
    return ToolResult.success(f"{header}\n{body}{suffix}")


def write_file(
    path: str,
    content: str,
    ctx: ToolContext,
    *,
    mode: str = "overwrite",
) -> ToolResult:
    """Write text to a file, creating parent directories as needed."""
    _require_files(ctx)
    if not ctx.allow_write:
        return ToolResult.failure("writing files is disabled (tools.allow_write is false)")

    target = ctx.resolve(path)
    if target.exists() and target.is_dir():
        return ToolResult.failure(f"{target} is a directory")

    append = mode == "append"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with target.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        else:
            # Same-directory temp file, then replace: a crash between the two
            # leaves either the old file or the new one, never a torn one.
            handle_fd, temp_name = tempfile.mkstemp(
                dir=str(target.parent), prefix=target.name, suffix=".tmp"
            )
            try:
                with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(content)
                os.replace(temp_name, target)
            except BaseException:
                Path(temp_name).unlink(missing_ok=True)
                raise
    except OSError as exc:
        return ToolResult.failure(f"Could not write {target}: {exc}")

    verb = "Appended to" if append else "Wrote"
    return ToolResult.success(f"{verb} {target} ({format_bytes(len(content.encode('utf-8')))}).")


def list_dir(
    ctx: ToolContext,
    path: str | None = None,
    *,
    depth: int = 1,
    max_entries: int = 400,
) -> ToolResult:
    """List a directory, optionally recursing a bounded number of levels.

    ``path`` defaults to the workspace root. It has to default here rather
    than only in the JSON schema: the schema saying "optional" while the
    function demands it made every bare ``list_dir()`` call fail with a
    TypeError instead of a listing.
    """
    _require_files(ctx)
    target = ctx.resolve(path, default=".")

    if not target.exists():
        return ToolResult.failure(f"No such directory: {target}")
    if not target.is_dir():
        return ToolResult.failure(f"{target} is a file, not a directory")

    entries: list[str] = []
    _walk(target, target, depth, entries, max_entries, ctx)

    if not entries:
        return ToolResult.success(f"{target} is empty")
    header = f"{target} ({len(entries)} entries shown, depth {max(1, depth)})"
    return ToolResult.success(f"{header}\n" + "\n".join(entries))


def _walk(
    directory: Path,
    root: Path,
    depth: int,
    entries: list[str],
    max_entries: int,
    ctx: ToolContext,
) -> None:
    """Depth-first listing that stops at the entry cap.

    Directories that are noise in every project are skipped, and symlinks are
    not followed - a listing should not walk out of the workspace or into a
    loop.
    """
    if depth <= 0 or len(entries) >= max_entries:
        return
    try:
        children = sorted(
            directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower())
        )
    except OSError as exc:
        entries.append(f"{_relative(directory, root)}  [unreadable: {exc}]")
        return

    for child in children:
        if len(entries) >= max_entries:
            entries.append("... [entry limit reached]")
            return
        name = child.name
        if name in {".git", "node_modules", "__pycache__", ".venv", "venv"}:
            continue
        relative = _relative(child, root)
        if child.is_symlink():
            entries.append(f"{relative}  -> symlink")
        elif child.is_dir():
            entries.append(f"{relative}/")
            _walk(child, root, depth - 1, entries, max_entries, ctx)
        else:
            try:
                size = format_bytes(child.stat().st_size)
            except OSError:
                size = "?"
            entries.append(f"{relative}  {size}")


def _relative(target: Path, root: Path) -> str:
    try:
        return str(target.relative_to(root))
    except ValueError:
        return str(target)
