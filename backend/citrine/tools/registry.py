"""The tool registry: what the agent can call, and how a call is dispatched.

One place defines each tool - its name, the description the model reads, its
JSON schema, and the callable behind it - so the three cannot drift apart. The
schema is what the provider sees; the description is what the model decides
from; keeping them adjacent means changing a tool's behaviour without changing
what the model is told about it becomes an obvious mistake rather than a hidden
one.

Dispatch is a dict lookup rather than a chain of ``if`` statements, and an
unknown tool name returns a readable failure instead of raising: a model that
hallucinates ``delete_everything`` should get told so, then answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from citrine.tools import files, git, network, terminal, web
from citrine.tools.base import ToolContext, ToolError, ToolResult


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    category: str
    run: Callable[..., ToolResult]
    # Whether the tool is usable at all under a given policy.
    enabled: Callable[[ToolContext], bool]
    disabled_reason: str


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="read_file",
        description=(
            "Read a file from the workspace. Text files come back with line "
            "numbers. Binary files (images, PDFs, archives, executables, "
            "Office documents) are described: their detected type, any text "
            "that can be extracted from a container such as .docx/.xlsx, and a "
            "base64 prefix of the raw bytes. Use start_line/max_lines to page "
            "through a large text file."
        ),
        parameters=_object(
            {
                "path": {
                    "type": "string",
                    "description": "File path, relative to the workspace root or absolute.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to return (1-based). Default 1.",
                },
                "max_lines": {
                    "type": "integer",
                    "description": "How many lines to return. Default 400.",
                },
                "as": {
                    "type": "string",
                    "enum": ["auto", "base64"],
                    "description": "'auto' decodes text and describes binary (default). 'base64' always describes the bytes.",
                },
            },
            ["path"],
        ),
        category="files",
        run=files.read_file,
        enabled=lambda ctx: ctx.allow_files,
        disabled_reason="file access is off (tools.allow_files)",
    ),
    Tool(
        name="write_file",
        description=(
            "Write text to a file, creating parent directories as needed. "
            "Overwrites by default; pass mode='append' to add to the end."
        ),
        parameters=_object(
            {
                "path": {"type": "string", "description": "File path to write."},
                "content": {"type": "string", "description": "Text to write."},
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append"],
                    "description": "Default 'overwrite'.",
                },
            },
            ["path", "content"],
        ),
        category="files",
        run=files.write_file,
        enabled=lambda ctx: ctx.allow_files and ctx.allow_write,
        disabled_reason="writing files is off (tools.allow_write)",
    ),
    Tool(
        name="list_dir",
        description=(
            "List the contents of a directory, with sizes. Directories are "
            "marked with a trailing slash. Use depth to recurse (default 1)."
        ),
        parameters=_object(
            {
                "path": {"type": "string", "description": "Directory path. Default '.'"},
                "depth": {
                    "type": "integer",
                    "description": "How many levels to recurse. Default 1.",
                },
            },
            [],
        ),
        category="files",
        run=files.list_dir,
        enabled=lambda ctx: ctx.allow_files,
        disabled_reason="file access is off (tools.allow_files)",
    ),
    Tool(
        name="run_command",
        description=(
            "Run a shell command in the workspace and return stdout, stderr and "
            "the exit code. This is a real shell with the user's permissions - "
            "use it for building, testing, running scripts, inspecting the "
            "machine, and installing things. Long-running commands should be "
            "given an explicit timeout_s."
        ),
        parameters=_object(
            {
                "command": {"type": "string", "description": "The command line to run."},
                "cwd": {
                    "type": "string",
                    "description": "Working directory, relative to the workspace root.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Seconds before the command is killed. Default 60.",
                },
            },
            ["command"],
        ),
        category="terminal",
        run=terminal.run_command,
        enabled=lambda ctx: ctx.allow_terminal,
        disabled_reason="terminal access is off (tools.allow_terminal)",
    ),
    Tool(
        name="git",
        description=(
            "Run a git command in the workspace: status, diff, log, add, branch, "
            "checkout, commit, push, and so on. Commits are credited to Citrine "
            "with a Co-Authored-By trailer. Pass arguments as a list, e.g. "
            "['status', '--short']."
        ),
        parameters=_object(
            {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Git arguments, without the leading 'git'.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Repository directory, relative to the workspace root.",
                },
            },
            ["args"],
        ),
        category="git",
        run=git.run_git,
        enabled=lambda ctx: ctx.allow_git,
        disabled_reason="git access is off (tools.allow_git)",
    ),
    Tool(
        name="fetch_url",
        description=(
            "Fetch an http/https URL and return the response as text (JSON is "
            "pretty-printed; binary responses are described). Supports GET, "
            "POST and other methods, with custom headers and a request body."
        ),
        parameters=_object(
            {
                "url": {"type": "string", "description": "Absolute http or https URL."},
                "method": {
                    "type": "string",
                    "description": "HTTP method. Default GET.",
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers as a JSON object.",
                },
                "body": {
                    "type": "string",
                    "description": "Request body, for POST/PUT.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Seconds before the request is abandoned. Default 30.",
                },
            },
            ["url"],
        ),
        category="network",
        run=network.fetch_url,
        enabled=lambda ctx: ctx.allow_network,
        disabled_reason="network access is off (tools.allow_network)",
    ),
    Tool(
        name="web_search",
        description=(
            "Search the web and get titles, URLs and snippets for the top "
            "results. No API key needed. Use fetch_url on a result to read the "
            "full page."
        ),
        parameters=_object(
            {
                "query": {"type": "string", "description": "What to search for."},
                "max_results": {
                    "type": "integer",
                    "description": "How many results to return. Default 8.",
                },
            },
            ["query"],
        ),
        category="network",
        run=web.web_search,
        enabled=lambda ctx: ctx.allow_network,
        disabled_reason="network access is off (tools.allow_network)",
    ),
)

TOOL_INDEX: dict[str, Tool] = {tool.name: tool for tool in TOOLS}


def enabled_tools(ctx: ToolContext) -> list[Tool]:
    return [tool for tool in TOOLS if tool.enabled(ctx)]


def specs(ctx: ToolContext) -> list[dict[str, Any]]:
    """The provider-facing tool list, filtered by policy."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in enabled_tools(ctx)
    ]


def execute(name: str, arguments: Any, ctx: ToolContext) -> ToolResult:
    """Run one tool call, returning a result rather than raising.

    Arguments arrive as a dict from most providers and as a JSON string from
    some; both are accepted. A tool that raises is caught here, because an
    exception in one tool should cost that call and not the conversation.
    """
    tool = TOOL_INDEX.get(name)
    if tool is None:
        known = ", ".join(sorted(TOOL_INDEX))
        return ToolResult.failure(f"Unknown tool: {name}. Available tools: {known}.")

    if not tool.enabled(ctx):
        return ToolResult.failure(f"{name} is not available: {tool.disabled_reason}.")

    params = _coerce_arguments(arguments)
    if isinstance(params, str):
        return ToolResult.failure(f"Could not parse arguments for {name}: {params}")

    try:
        return tool.run(ctx=ctx, **params)
    except ToolError as exc:
        # A policy refusal or a missing-file complaint: the message is the
        # whole point, so it is passed through unwrapped.
        return ToolResult.failure(str(exc))
    except TypeError as exc:
        # Wrong or missing arguments for this tool: say which call was wrong
        # rather than reporting an internal error.
        return ToolResult.failure(
            f"Bad arguments for {name}: {exc}. Expected schema: "
            f"{json.dumps(tool.parameters)}"
        )
    except Exception as exc:  # noqa: BLE001 - one tool must not kill the turn
        return ToolResult.failure(f"{name} failed: {type(exc).__name__}: {exc}")


def _coerce_arguments(arguments: Any) -> dict[str, Any] | str:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return {str(key): value for key, value in arguments.items()}
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return f"invalid JSON ({exc})"
        if isinstance(parsed, dict):
            return {str(key): value for key, value in parsed.items()}
        return f"expected a JSON object, got {type(parsed).__name__}"
    return f"expected an object or JSON string, got {type(arguments).__name__}"
