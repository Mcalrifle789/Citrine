"""The agent's tools.

Import surface for the rest of the backend: the registry (what exists and how
to call it), the context that carries the user's policy, and the helpers that
turn a config file into a context.
"""

from __future__ import annotations

from pathlib import Path

from citrine.tools import git, magic, network, terminal
from citrine.tools.base import ToolContext, ToolError, ToolResult, format_bytes, truncate
from citrine.tools.registry import TOOLS, TOOL_INDEX, enabled_tools, execute, specs

__all__ = [
    "TOOLS",
    "TOOL_INDEX",
    "ToolContext",
    "ToolError",
    "ToolResult",
    "build_context",
    "enabled_tools",
    "execute",
    "format_bytes",
    "git",
    "magic",
    "network",
    "specs",
    "terminal",
    "truncate",
]


def build_context(config, workspace: str | Path | None = None) -> ToolContext:
    """Turn a CitrineConfig plus a workspace into a ToolContext.

    Resolution order for the root: an explicit workspace argument (what the
    app passes down from Electron), then the configured workspace_root, then
    the process working directory as the last resort.
    """
    settings = getattr(config, "tools", None)

    root_value = ""
    if isinstance(workspace, Path):
        root_value = str(workspace)
    elif isinstance(workspace, str) and workspace.strip():
        root_value = workspace.strip()
    elif settings is not None and getattr(settings, "workspace_root", ""):
        root_value = settings.workspace_root

    # The home directory, not the process cwd: the backend is spawned with
    # cwd=backend/, which is meaningless to the user, whereas ~ is where their
    # files actually are. An explicit workspace argument or a configured
    # workspace_root wins over this.
    root = Path(root_value).expanduser() if root_value else Path.home()
    try:
        root = root.resolve()
    except OSError:  # pragma: no cover - platform specific
        root = Path.cwd()

    if settings is None:
        return ToolContext(root=root)

    return ToolContext(
        root=root,
        allow_files=bool(settings.allow_files),
        allow_write=bool(settings.allow_write),
        allow_terminal=bool(settings.allow_terminal),
        allow_git=bool(settings.allow_git),
        allow_network=bool(settings.allow_network),
        allow_destructive=bool(settings.allow_destructive),
        allow_outside_workspace=bool(settings.allow_outside_workspace),
        timeout_s=int(settings.command_timeout_s),
        max_output_chars=int(settings.max_output_chars),
        max_file_bytes=int(settings.max_file_bytes),
    )
