"""Slash command registry for the shell-spine build.

This is intentionally lightweight: it gives every advertised command a real
backend path today, while the heavier provider, search, agent, and tool
systems can replace individual handlers in later slices.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    name: str
    description: str


COMMANDS: tuple[Command, ...] = (
    Command("provider", "Add or switch model providers"),
    Command("model", "Browse models from the selected provider"),
    Command("keys", "Manage stored API keys"),
    Command("mcp", "Connect ElevenLabs, Deepgram, SUNO, or custom MCP"),
    Command(
        "searchsetup",
        "Configure DuckDuckGo, Perplexity, Gemini, Parallel, or custom search",
    ),
    Command("theme", "Switch visual themes"),
    Command("settings", "Open Citrine settings"),
    Command("chat", "Start a new chat session"),
    Command("plan", "Enter planning mode"),
    Command("build", "Enter execution mode"),
    Command("memory", "View or edit saved memory"),
    Command("context", "Inspect active context"),
    Command("summarize", "Summarize the session"),
    Command("fork", "Branch this conversation"),
    Command("sessions", "Switch between agent sessions"),
    Command("agent", "Switch agents or create a new one"),
    Command("tasks", "View active agent tasks"),
    Command("tools", "Inspect enabled tools"),
    Command("approvals", "Review pending confirmations"),
    Command("schedule", "Create a scheduled task"),
    Command("code", "Generate or refactor code"),
    Command("explain", "Explain code or concepts"),
    Command("refactor", "Improve existing code"),
    Command("test", "Generate or run tests"),
    Command("docs", "Generate documentation"),
    Command("review", "Review code for bugs"),
    Command("debug", "Diagnose errors"),
    Command("diff", "Inspect current changes"),
    Command("patch", "Apply a focused patch"),
    Command("commit", "Create a git commit"),
    Command("git", "Inspect branches and history"),
    Command("init", "Initialize a project"),
    Command("open", "Open a project"),
    Command("files", "Browse project files"),
    Command("workspace", "Manage workspace roots"),
    Command("run", "Run a project command"),
    Command("terminal", "Open a shell pane"),
    Command("deploy", "Deploy the project"),
    Command("env", "Manage environment variables"),
    Command("package", "Build or package the app"),
    Command("update", "Check for updates"),
    Command("desktop", "Request desktop control"),
    Command("screenshot", "Capture the screen"),
    Command("browse", "Open a browser task"),
    Command("search", "Search through the configured search provider"),
    Command("web", "Fetch or inspect web pages"),
    Command("research", "Run a research pass"),
    Command("notes", "Open local notes"),
    Command("speak", "Generate speech with ElevenLabs"),
    Command("listen", "Start voice input"),
    Command("transcribe", "Transcribe audio with Deepgram"),
    Command("voice", "Manage voices"),
    Command("music", "Generate music with SUNO"),
    Command("clone", "Duplicate or transform audio"),
    Command("media", "View generated media assets"),
    Command("spotify", "Browse or play Spotify"),
    Command("calendar", "Inspect calendar context"),
    Command("inbox", "Triage messages or email"),
    Command("commands", "Open the full command catalog"),
    Command("history", "Browse previous sessions"),
    Command("export", "Export chats or artifacts"),
    Command("reset", "Reset session state"),
    Command("logs", "Open app and backend logs"),
    Command("health", "Run Citrine diagnostics"),
    Command("status", "Show current system status"),
    Command("help", "Show help information"),
)

COMMAND_INDEX = {command.name: command for command in COMMANDS}


def run_command(raw: str) -> str:
    """Return a command response for a slash-command prompt value."""
    value = raw.strip()
    if not value.startswith("/"):
        return raw

    head = value[1:].split(maxsplit=1)[0].lower()
    command = COMMAND_INDEX.get(head)
    if command is None:
        return (
            f"Unknown command: /{head}\n"
            "Type /commands to see the command catalog."
        )

    if head in {"help", "commands"}:
        return _command_catalog()
    if head == "provider":
        return _provider_help()
    if head == "model":
        return _model_help()
    if head == "mcp":
        return _mcp_help()
    if head == "searchsetup":
        return _search_setup_help()
    if head == "sessions":
        return _sessions_help()
    if head == "agent":
        return _agent_help()
    if head == "status":
        return "Citrine status\nBackend: connected\nMode: Plan\nCommands: 66"
    if head == "health":
        return "Citrine health\nBackend websocket: ok\nCommand registry: ok"

    return (
        f"/{command.name} - {command.description}\n"
        "Command recognized. Full workflow implementation is coming in a later slice."
    )


def _command_catalog() -> str:
    lines = ["Citrine commands"]
    lines.extend(f"/{command.name} - {command.description}" for command in COMMANDS)
    return "\n".join(lines)


def _provider_help() -> str:
    return "\n".join(
        [
            "Provider setup",
            "Use /provider to add or switch model providers.",
            "Planned providers include OpenRouter, Opencode, Kilo, LiteLLM, Anthropic, OpenAI, Groq, DeepInfra, and custom OpenAI-compatible endpoints.",
            "When provider setup is wired, Citrine will ask for the provider fields and store secrets through the OS credential store.",
        ]
    )


def _model_help() -> str:
    return "\n".join(
        [
            "Model browser",
            "Use /model after selecting a provider.",
            "Citrine will query the selected provider and show only models available to that API key.",
        ]
    )


def _mcp_help() -> str:
    return "\n".join(
        [
            "MCP setup",
            "Use /mcp to connect ElevenLabs, Deepgram, SUNO, or a custom MCP service.",
            "Each connector will request its API key, validate it, and store it through the OS credential store.",
        ]
    )


def _search_setup_help() -> str:
    return "\n".join(
        [
            "Search provider setup",
            "Use /searchsetup to configure DuckDuckGo, Perplexity, Google Gemini, Parallel, Parallel Free, or a custom search provider.",
            "Once configured, /search and /research will use the selected search provider.",
        ]
    )


def _sessions_help() -> str:
    return "\n".join(
        [
            "Agent sessions",
            "Use /sessions to switch between active sessions for the current or selected agent.",
            "Session persistence will live under the Citrine data directory once the agent system is wired.",
        ]
    )


def _agent_help() -> str:
    return "\n".join(
        [
            "Agent manager",
            "Use /agent to switch agents or create a new agent with a name and goal.",
            "Agent files will be saved under Documents/Citrine/Agents.",
        ]
    )
