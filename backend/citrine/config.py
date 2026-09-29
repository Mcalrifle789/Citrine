"""Persistent Citrine setup and runtime configuration."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from citrine.paths import config_path, ensure_dirs


@dataclass
class ProviderConfig:
    id: str
    label: str
    base_url: str | None = None
    model: str | None = None


@dataclass
class SearchConfig:
    id: str
    label: str


@dataclass
class MusicPluginConfig:
    id: str
    label: str


@dataclass
class AgentConfig:
    name: str = "Default"
    provider_id: str | None = None
    model: str | None = None


@dataclass
class ToolsConfig:
    """What the agent is allowed to do inside a conversation.

    These defaults are deliberately permissive: Citrine is a local-first
    personal agent, and an agent that cannot touch the machine is the thing
    this config exists to stop being. The guards that remain are the ones that
    protect against an accident rather than a decision - a timeout so a hung
    command cannot wedge the chat, an output cap so a runaway build cannot
    crowd the context window, and ``allow_destructive`` off so the handful of
    commands that destroy work without asking are refused unless the user opts
    in.

    ``workspace_root`` is the directory file tools treat as home base and the
    directory commands run in. Empty means "the user's home directory". Paths
    outside the root are allowed by default - this is a personal agent on the
    user's own machine, and a wall it keeps bumping into is worse than one it
    can see - but ``allow_outside_workspace`` turns the wall back on.
    """

    enabled: bool = True
    allow_files: bool = True
    allow_write: bool = True
    allow_terminal: bool = True
    allow_git: bool = True
    allow_network: bool = True
    allow_destructive: bool = False
    allow_outside_workspace: bool = True
    workspace_root: str = ""
    command_timeout_s: int = 60
    max_output_chars: int = 20_000
    max_file_bytes: int = 200_000
    max_rounds: int = 8


@dataclass
class CitrineConfig:
    username: str = ""
    password_hash: str = ""
    password_salt: str = ""
    providers: list[ProviderConfig] = field(default_factory=list)
    active_provider_id: str | None = None
    search_provider: SearchConfig | None = None
    music_plugins: list[MusicPluginConfig] = field(default_factory=list)
    theme: str = "citrine"
    active_session: str = "main"
    sessions: list[str] = field(default_factory=lambda: ["main"])
    # Keyed by ``usage_key(agent, session)``, not by session alone: an agent
    # switch usually changes the model, and a token count measured against a
    # different context window is not the same number. See usage_key().
    token_usage: dict[str, int] = field(default_factory=dict)
    active_agent: str = "Default"
    agents: list[AgentConfig] = field(default_factory=lambda: [AgentConfig()])
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    # Bumped whenever the visible transcript should be thrown away without the
    # agent or session name changing (``/reset``). The renderer keys its
    # scrollback on transcript_key(), so a bump blanks the window.
    transcript_epoch: int = 0
    # One provider HTTP call. Reasoning models routinely spend more than a
    # minute on a single completion, so this is well above urllib's default.
    request_timeout_s: int = 180
    # Wall clock for a whole turn, tool rounds included. Without it a turn is
    # bounded only by max_rounds * request_timeout_s, which is long enough to
    # look like a hang.
    turn_budget_s: int = 600

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CitrineConfig":
        return cls(
            username=str(data.get("username", "")),
            password_hash=str(data.get("password_hash", "")),
            password_salt=str(data.get("password_salt", "")),
            providers=[ProviderConfig(**item) for item in data.get("providers", [])],
            active_provider_id=data.get("active_provider_id"),
            search_provider=(
                SearchConfig(**data["search_provider"])
                if data.get("search_provider")
                else None
            ),
            music_plugins=[
                MusicPluginConfig(**item) for item in data.get("music_plugins", [])
            ],
            theme=str(data.get("theme", "citrine")),
            active_session=str(data.get("active_session", "main")),
            sessions=list(data.get("sessions", ["main"])),
            token_usage=_usage_from_dict(
                data.get("token_usage"), str(data.get("active_agent", "Default"))
            ),
            active_agent=str(data.get("active_agent", "Default")),
            agents=[AgentConfig(**item) for item in data.get("agents", [{"name": "Default"}])],
            tools=_tools_from_dict(data.get("tools")),
            transcript_epoch=_non_negative_int(data.get("transcript_epoch"), 0),
            request_timeout_s=_non_negative_int(data.get("request_timeout_s"), 180),
            turn_budget_s=_non_negative_int(data.get("turn_budget_s"), 600),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def active_provider(self) -> ProviderConfig | None:
        for provider in self.providers:
            if provider.id == self.active_provider_id:
                return provider
        return self.providers[0] if self.providers else None

    def active_agent_config(self) -> AgentConfig:
        for agent in self.agents:
            if agent.name == self.active_agent:
                return agent
        agent = AgentConfig(name=self.active_agent)
        self.agents.append(agent)
        return agent

    def usage_key(self) -> str:
        """The token-usage bucket for the active agent and session."""
        return usage_key(self.active_agent, self.active_session)

    def session_tokens(self) -> int:
        return self.token_usage.get(self.usage_key(), 0)

    def add_session_tokens(self, tokens: int, key: str | None = None) -> None:
        """Charge ``tokens`` to a usage bucket, the active one by default.

        ``key`` exists for work that changes which bucket is active while it
        runs: ``/new`` has to be charged to the session it was typed in, or it
        lands on the session it just created and undoes its own reset.
        """
        bucket = key or self.usage_key()
        self.token_usage[bucket] = self.token_usage.get(bucket, 0) + max(0, tokens)

    def reset_session_tokens(self) -> None:
        self.token_usage[self.usage_key()] = 0

    def transcript_key(self) -> str:
        """Identity of the visible scrollback.

        The renderer clears and re-keys its transcript whenever this string
        changes, so a new session, a session switch, an agent switch, and
        ``/reset`` all blank the window without needing their own protocol
        message.
        """
        return f"{self.usage_key()}#{self.transcript_epoch}"


def usage_key(agent: str, session: str) -> str:
    """Bucket name for one agent's usage within one session."""
    return f"{agent}::{session}"


def _non_negative_int(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return max(0, value)


def _usage_from_dict(data: Any, active_agent: str) -> dict[str, int]:
    """Read stored token usage, migrating pre-agent keys.

    Older builds keyed usage by session name alone. Those counts are attributed
    to the agent that was active when the file was written, which is the only
    agent they could have belonged to on a single-agent config and a harmless
    guess otherwise - the alternative is silently dropping the user's usage.
    """
    if not isinstance(data, dict):
        return {}
    usage: dict[str, int] = {}
    for key, value in data.items():
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        name = str(key)
        if "::" not in name:
            name = usage_key(active_agent, name)
        usage[name] = max(0, value)
    return usage


def _tools_from_dict(data: Any) -> ToolsConfig:
    """Build a ToolsConfig from stored JSON, ignoring unknown or bad keys.

    A config file written by an older build must not break the chat path, so
    unrecognised keys are dropped and wrong types fall back to the default
    rather than raising.
    """
    config = ToolsConfig()
    if not isinstance(data, dict):
        return config
    for key, value in data.items():
        if not hasattr(config, key):
            continue
        current = getattr(config, key)
        if isinstance(current, bool):
            if isinstance(value, bool):
                setattr(config, key, value)
        elif isinstance(current, int):
            if isinstance(value, int) and not isinstance(value, bool):
                setattr(config, key, max(0, value))
        elif isinstance(current, str):
            if isinstance(value, str):
                setattr(config, key, value)
    return config


def load_config(path: Path | None = None) -> CitrineConfig:
    target = path or config_path()
    if not target.exists():
        return CitrineConfig()
    return CitrineConfig.from_dict(json.loads(target.read_text(encoding="utf-8")))


def save_config(config: CitrineConfig, path: Path | None = None) -> None:
    ensure_dirs()
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    actual_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(actual_salt),
        210_000,
    )
    return actual_salt, digest.hex()
