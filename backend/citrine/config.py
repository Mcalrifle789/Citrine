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
