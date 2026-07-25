"""Slash command registry for the shell-spine build.

This is intentionally lightweight: it gives every advertised command a real
backend path today, while the heavier provider, search, agent, and tool
systems can replace individual handlers in later slices.
"""

from __future__ import annotations

from dataclasses import dataclass

from citrine.config import AgentConfig, CitrineConfig


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
    Command("new", "Start a new session"),
    Command("plan", "Enter planning mode"),
    Command("build", "Enter execution mode"),
    Command("memory", "View or edit saved memory"),
    Command("context", "Inspect active context"),
    Command("summarize", "Summarize the session"),
    Command("fork", "Branch this conversation"),
    Command("session", "Switch between agent sessions"),
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

THEMES = ("citrine", "midnight", "ember", "matrix", "violet", "mono")


def run_command(raw: str, config: CitrineConfig | None = None) -> str:
    """Return a command response for a slash-command prompt value."""
    cfg = config or CitrineConfig()
    value = raw.strip()
    if not value.startswith("/"):
        return raw

    parts = value[1:].split(maxsplit=1)
    head = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    command = COMMAND_INDEX.get(head)
    if command is None:
        return (
            f"Unknown command: /{head}\n"
            "Type /commands to see the command catalog."
        )

    if head in {"help", "commands"}:
        return _command_catalog()
    if head == "provider":
        return _provider_command(arg, cfg)
    if head == "model":
        return _model_command(arg, cfg)
    if head == "mcp":
        return _mcp_help()
    if head == "searchsetup":
        return _search_setup_help()
    if head == "theme":
        return _theme_command(arg, cfg)
    if head == "session":
        return _session_command(arg, cfg)
    if head == "new":
        return _new_session(cfg)
    if head == "agent":
        return _agent_command(arg, cfg)
    if head == "status":
        return _status(cfg)
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
            "Use /provider to switch model providers.",
            "Run `citrine setup` to add providers and API keys.",
            "Examples: /provider openrouter, /provider openai, /provider custom",
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


def _theme_command(arg: str, config: CitrineConfig) -> str:
    if not arg:
        return "Themes\n" + "\n".join(
            f"{'*' if theme == config.theme else ' '} /theme {theme}"
            for theme in THEMES
        )
    theme = arg.lower()
    if theme not in THEMES:
        return f"Unknown theme: {arg}\nAvailable: {', '.join(THEMES)}"
    config.theme = theme
    return f"Theme switched to {theme}."


def _provider_command(arg: str, config: CitrineConfig) -> str:
    if not config.providers:
        return _provider_help()
    if not arg:
        lines = ["Providers"]
        for provider in config.providers:
            active = "*" if provider.id == config.active_provider_id else " "
            lines.append(f"{active} /provider {provider.id} - {provider.label}")
        return "\n".join(lines)
    wanted = arg.lower()
    for provider in config.providers:
        if wanted in {provider.id, provider.label.lower()}:
            config.active_provider_id = provider.id
            agent = config.active_agent_config()
            agent.provider_id = provider.id
            agent.model = provider.model
            return f"Provider switched to {provider.label}."
    return f"Provider is not configured: {arg}\nRun `citrine setup` to add it."


def _model_command(arg: str, config: CitrineConfig) -> str:
    provider = config.active_provider()
    if provider is None:
        return "No provider is configured. Run `citrine setup` first."
    agent = config.active_agent_config()
    if not arg:
        return (
            f"Active provider: {provider.label}\n"
            f"Current model: {agent.model or provider.model or 'not set'}\n"
            "Use /model <model-name> to switch."
        )
    provider.model = arg
    agent.provider_id = provider.id
    agent.model = arg
    return f"Model switched to {arg} for agent {agent.name}."


def _session_command(arg: str, config: CitrineConfig) -> str:
    if not arg:
        return "Sessions\n" + "\n".join(
            f"{'*' if session == config.active_session else ' '} /session {session}"
            for session in config.sessions
        )
    if arg not in config.sessions:
        config.sessions.append(arg)
        config.token_usage[arg] = 0
    config.active_session = arg
    return f"Session switched to {arg}."


def _new_session(config: CitrineConfig) -> str:
    base = "session"
    index = 1
    while f"{base}-{index}" in config.sessions:
        index += 1
    name = f"{base}-{index}"
    config.sessions.append(name)
    config.active_session = name
    config.token_usage[name] = 0
    return f"New session created: {name}."


def _agent_command(arg: str, config: CitrineConfig) -> str:
    if not arg:
        return "Agents\n" + "\n".join(
            f"{'*' if agent.name == config.active_agent else ' '} /agent {agent.name}"
            for agent in config.agents
        ) + "\nUse /agent <name> to switch or create."
    for agent in config.agents:
        if agent.name.lower() == arg.lower():
            config.active_agent = agent.name
            return f"Agent switched to {agent.name}."
    provider = config.active_provider()
    model = provider.model if provider else None
    config.agents.append(
        AgentConfig(
            name=arg,
            provider_id=provider.id if provider else None,
            model=model,
        )
    )
    config.active_agent = arg
    return f"Agent created: {arg} ({model or 'no model selected'})."


def _status(config: CitrineConfig) -> str:
    provider = config.active_provider()
    agent = config.active_agent_config()
    return "\n".join(
        [
            "Citrine status",
            "Backend: connected",
            f"User: {config.username or 'not setup'}",
            f"Agent: {agent.name}",
            f"Session: {config.active_session}",
            f"Provider: {provider.label if provider else 'not configured'}",
            f"Model: {agent.model or (provider.model if provider else None) or 'not set'}",
            f"Search: {config.search_provider.label if config.search_provider else 'not configured'}",
            f"Theme: {config.theme}",
            f"Commands: {len(COMMANDS)}",
        ]
    )
