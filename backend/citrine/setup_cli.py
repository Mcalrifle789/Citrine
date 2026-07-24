"""Interactive terminal setup for ``citrine setup``."""

from __future__ import annotations

import getpass
import sys

from citrine.catalog import CHAT_PROVIDERS, MUSIC_PLUGINS, SEARCH_PROVIDERS
from citrine.config import (
    AgentConfig,
    CitrineConfig,
    MusicPluginConfig,
    ProviderConfig,
    SearchConfig,
    hash_password,
    save_config,
)
from citrine.secrets_store import secret_key, store_secret


def main() -> None:
    print("Citrine setup")
    print("Use search text to filter lists. Use comma-separated numbers for multi-select.")
    print()

    username = _required("Step 1 - username: ")
    password = _secret_prompt("Step 1 - password (Tab toggles visibility): ")
    salt, digest = hash_password(password)

    providers = _select_many("Step 2 - model providers", CHAT_PROVIDERS)
    provider_configs: list[ProviderConfig] = []
    for provider in providers:
        base_url = provider.base_url
        if provider.id in {"custom", "opencode", "kilo"} and not base_url:
            base_url = _required(f"{provider.label} base URL: ")
        model = input(f"{provider.label} default model [{provider.default_model or 'manual later'}]: ").strip()
        api_key = _secret_prompt(f"{provider.label} API key (Tab toggles visibility): ")
        store = store_secret(secret_key("provider", provider.id), api_key)
        if store == "local-fallback":
            print("  warning: OS keyring unavailable; stored in Citrine local fallback.")
        provider_configs.append(
            ProviderConfig(
                id=provider.id,
                label=provider.label,
                base_url=base_url,
                model=model or provider.default_model,
            )
        )

    search = _select_one("Step 3 - search provider", SEARCH_PROVIDERS)
    if search.env_var is not None:
        api_key = _secret_prompt(f"{search.label} API key (Tab toggles visibility): ")
        store = store_secret(secret_key("search", search.id), api_key)
        if store == "local-fallback":
            print("  warning: OS keyring unavailable; stored in Citrine local fallback.")
    else:
        print(f"{search.label} does not require an API key.")

    music = _select_many("Step 4 - optional music/audio plugins", MUSIC_PLUGINS, allow_empty=True)
    music_configs: list[MusicPluginConfig] = []
    for plugin in music:
        api_key = _secret_prompt(f"{plugin.label} API key (Tab toggles visibility): ")
        store = store_secret(secret_key("music", plugin.id), api_key)
        if store == "local-fallback":
            print("  warning: OS keyring unavailable; stored in Citrine local fallback.")
        music_configs.append(MusicPluginConfig(id=plugin.id, label=plugin.label))

    active_provider = provider_configs[0] if provider_configs else None
    config = CitrineConfig(
        username=username,
        password_hash=digest,
        password_salt=salt,
        providers=provider_configs,
        active_provider_id=active_provider.id if active_provider else None,
        search_provider=SearchConfig(id=search.id, label=search.label),
        music_plugins=music_configs,
        agents=[
            AgentConfig(
                name="Default",
                provider_id=active_provider.id if active_provider else None,
                model=active_provider.model if active_provider else None,
            )
        ],
    )
    save_config(config)

    print()
    print("Setup complete.")
    print("Run `citrine` to open the app, or `citrine setup` again to reconfigure.")


def _required(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Required.")


def _select_many(title: str, items, allow_empty: bool = False):
    while True:
        matches = _search_items(title, items)
        raw = input("Select numbers separated by commas: ").strip()
        if allow_empty and raw == "":
            return []
        try:
            indexes = [int(part.strip()) - 1 for part in raw.split(",") if part.strip()]
            selected = [matches[index] for index in indexes]
        except (ValueError, IndexError):
            print("Invalid selection.")
            continue
        if selected or allow_empty:
            return selected
        print("Pick at least one.")


def _select_one(title: str, items):
    while True:
        matches = _search_items(title, items)
        raw = input("Select one number: ").strip()
        try:
            return matches[int(raw) - 1]
        except (ValueError, IndexError):
            print("Invalid selection.")


def _search_items(title: str, items):
    while True:
        query = input(f"{title} search (blank shows all): ").strip().lower()
        matches = [
            item
            for item in items
            if not query or query in item.id.lower() or query in item.label.lower()
        ]
        if matches:
            for idx, item in enumerate(matches, start=1):
                print(f"  {idx}. {item.label} ({item.id})")
            return matches
        print("No matches.")


def _secret_prompt(prompt: str) -> str:
    if sys.platform == "win32":
        return _windows_secret_prompt(prompt)
    return getpass.getpass(prompt).strip()


def _windows_secret_prompt(prompt: str) -> str:
    import msvcrt

    visible = False
    chars: list[str] = []
    sys.stdout.write(prompt)
    sys.stdout.flush()
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            sys.stdout.write("\n")
            value = "".join(chars).strip()
            if value:
                return value
            print("Required.")
            sys.stdout.write(prompt)
            chars.clear()
            continue
        if ch == "\t":
            visible = not visible
            sys.stdout.write("\r" + " " * (len(prompt) + max(len(chars), 8) + 24) + "\r")
            sys.stdout.write(prompt + ("".join(chars) if visible else "*" * len(chars)))
            sys.stdout.flush()
            continue
        if ch in ("\b", "\x7f"):
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
            continue
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch:
            chars.append(ch)
            sys.stdout.write(ch if visible else "*")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
