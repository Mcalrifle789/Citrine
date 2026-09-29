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

    ``workspace_root`` is the directory file tools are confined to and the
    directory commands run in. Empty means "use the process working directory",
    which Electron sets to the project root when it spawns the sidecar.
    """

    enabled: bool = True
    allow_files: bool = True
    allow_write: bool = True
    allow_terminal: bool = True
    allow_git: bool = True
    allow_network: bool = True
    allow_destructive: bool = False
    allow_outside_workspace: bool = False
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
    token_usage: dict[str, int] = field(default_factory=dict)
    active_agent: str = "Default"
    agents: list[AgentConfig] = field(default_factory=lambda: [AgentConfig()])
    tools: ToolsConfig = field(default_factory=ToolsConfig)

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
            token_usage={
                str(key): int(value)
                for key, value in data.get("token_usage", {}).items()
            },
            active_agent=str(data.get("active_agent", "Default")),
            agents=[AgentConfig(**item) for item in data.get("agents", [{"name": "Default"}])],
            tools=_tools_from_dict(data.get("tools")),
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
