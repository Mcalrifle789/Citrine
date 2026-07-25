"""Interactive terminal setup for ``citrine setup``."""

from __future__ import annotations

import getpass
import os
import sys
from dataclasses import dataclass
from typing import Sequence

from citrine.catalog import CHAT_PROVIDERS, MUSIC_PLUGINS, SEARCH_PROVIDERS, ProviderDescriptor
from citrine.config import (
    AgentConfig,
    CitrineConfig,
    MusicPluginConfig,
    ProviderConfig,
    SearchConfig,
    hash_password,
    load_config,
    save_config,
)
from citrine.paths import config_path
from citrine.secrets_store import secret_key, store_secret

WIDTH = 78


@dataclass
class SecretWrite:
    key: str
    value: str


def main() -> None:
    try:
        wizard = SetupWizard()
        wizard.run()
    except KeyboardInterrupt:
        print("\nSetup cancelled. Nothing was saved.")
        raise SystemExit(130)


class SetupWizard:
    def __init__(self) -> None:
        self.existing = load_config()
        self.secrets: list[SecretWrite] = []

    def run(self) -> None:
        _clear()
        _banner()
        if config_path().exists():
            print(f"Existing config: {config_path()}")
            if not _confirm("Overwrite it with a fresh setup?", default=False):
                print("Leaving existing setup unchanged.")
                return

        username, password_hash, password_salt = self._account_step()
        providers = self._providers_step()
        search = self._search_step()
        music = self._music_step()

        active = providers[0]
        config = CitrineConfig(
            username=username,
            password_hash=password_hash,
            password_salt=password_salt,
            providers=providers,
            active_provider_id=active.id,
            search_provider=search,
            music_plugins=music,
            theme=self.existing.theme,
            agents=[
                AgentConfig(
                    name="Default",
                    provider_id=active.id,
                    model=active.model,
                )
            ],
        )

        self._review(config)
        if not _confirm("Save this setup?", default=True):
            print("Setup discarded. Nothing was saved.")
            return

        for secret in self.secrets:
            store = store_secret(secret.key, secret.value)
            if store == "local-fallback":
                print("warning: OS keyring unavailable; used Citrine local fallback.")
        save_config(config)
        _section("Complete", "Citrine is ready.")
        print("Run `citrine` to open the app.")

    def _account_step(self) -> tuple[str, str, str]:
        _section("Step 1/4", "Account")
        print("Create local credentials for this Citrine profile.")
        username = _required("Username", default=self.existing.username or None)
        while True:
            password = _secret_prompt("Password (Tab toggles visibility)")
            score, notes = _password_score(password)
            if score < 3:
                print("Password is too weak: " + "; ".join(notes))
                continue
            confirm = _secret_prompt("Confirm password")
            if password != confirm:
                print("Passwords did not match.")
                continue
            salt, digest = hash_password(password)
            return username, digest, salt

    def _providers_step(self) -> list[ProviderConfig]:
        _section("Step 2/4", "Model providers")
        print("Pick one or more providers. Citrine can switch between them later with /provider.")
        selected = _pick_many(CHAT_PROVIDERS, allow_empty=False)
        providers: list[ProviderConfig] = []
        for index, provider in enumerate(selected, start=1):
            _card(f"Provider {index}: {provider.label}")
            label = provider.label
            if provider.id == "custom":
                label = _required("Display name", default="Custom Provider")
            base_url = provider.base_url
            if provider.id in {"custom", "opencode", "kilo"} and not base_url:
                base_url = _required("Base URL, ending before /chat/completions")
            model = _optional(
                "Default model",
                default=provider.default_model,
                hint="leave blank if you want to choose inside Citrine",
            )
            self._collect_secret("provider", provider, required=True)
            providers.append(
                ProviderConfig(
                    id=provider.id,
                    label=label,
                    base_url=base_url,
                    model=model or provider.default_model,
                )
            )
        return providers

    def _search_step(self) -> SearchConfig:
        _section("Step 3/4", "Search provider")
        print("Pick exactly one search provider. /search and /research will use this provider.")
        provider = _pick_one(SEARCH_PROVIDERS)
        self._collect_secret("search", provider, required=provider.env_var is not None)
        return SearchConfig(id=provider.id, label=provider.label)

    def _music_step(self) -> list[MusicPluginConfig]:
        _section("Step 4/4", "Music and audio plugins")
        print("Optional. Pick none, one, or many. These power speech, transcription, and music commands.")
        selected = _pick_many(MUSIC_PLUGINS, allow_empty=True)
        plugins: list[MusicPluginConfig] = []
        for plugin in selected:
            _card(plugin.label)
            self._collect_secret("music", plugin, required=True)
            plugins.append(MusicPluginConfig(id=plugin.id, label=plugin.label))
        return plugins

    def _collect_secret(
        self,
        kind: str,
        item: ProviderDescriptor,
        required: bool,
    ) -> None:
        if item.env_var and os.environ.get(item.env_var):
            print(f"Using environment variable {item.env_var}; no key entry needed.")
            return
        if not required:
            print(f"{item.label} does not require an API key.")
            return
        value = _secret_prompt(f"{item.label} API key (Tab toggles visibility)")
        self.secrets.append(SecretWrite(secret_key(kind, item.id), value))

    def _review(self, config: CitrineConfig) -> None:
        _section("Review", "Nothing is saved until you confirm.")
        print(f"Config file: {config_path()}")
        print(f"User: {config.username}")
        print(f"Active provider: {config.active_provider_id}")
        print("Providers:")
        for provider in config.providers:
            print(f"  - {provider.label} ({provider.id}) model={provider.model or 'manual'}")
        print(f"Search: {config.search_provider.label if config.search_provider else 'none'}")
        if config.music_plugins:
            print("Music/audio: " + ", ".join(plugin.label for plugin in config.music_plugins))
        else:
            print("Music/audio: none")
        print(f"Secrets to store: {len(self.secrets)}")


def _pick_many(items: Sequence[ProviderDescriptor], allow_empty: bool) -> list[ProviderDescriptor]:
    picked = _questionary_checkbox(items, allow_empty)
    if picked is not None:
        return picked

    selected: list[ProviderDescriptor] = []
    while True:
        _table(items, selected)
        prompt = "Select numbers, `all`, `done`"
        if allow_empty:
            prompt += ", or `skip`"
        raw = input(f"{prompt}: ").strip().lower()
        if raw == "done" and (selected or allow_empty):
            return selected
        if raw == "skip" and allow_empty:
            return []
        if raw == "all":
            selected = list(items)
            continue
        try:
            for index in _parse_indexes(raw, len(items)):
                item = items[index]
                if item in selected:
                    selected.remove(item)
                else:
                    selected.append(item)
        except ValueError as exc:
            print(exc)
            continue


def _pick_one(items: Sequence[ProviderDescriptor]) -> ProviderDescriptor:
    picked = _questionary_select(items)
    if picked is not None:
        return picked

    while True:
        _table(items, [])
        raw = input("Select one number: ").strip().lower()
        try:
            indexes = _parse_indexes(raw, len(items))
            if len(indexes) != 1:
                raise ValueError("Pick exactly one item.")
            return items[indexes[0]]
        except ValueError as exc:
            print(exc)


def _questionary_checkbox(
    items: Sequence[ProviderDescriptor],
    allow_empty: bool,
) -> list[ProviderDescriptor] | None:
    try:
        import questionary
        from questionary import Choice
    except Exception:
        return None

    choices = [
        Choice(title=_choice_title(item), value=item)
        for item in items
    ]
    while True:
        selected = questionary.checkbox(
            "Scroll, click, or press Space to toggle. Enter confirms.",
            choices=choices,
            style=_questionary_style(),
            pointer=">",
            qmark="",
            use_jk_keys=True,
            mouse_support=True,
        ).ask()
        if selected is None:
            raise KeyboardInterrupt
        if selected or allow_empty:
            return list(selected)
        print("Pick at least one.")


def _questionary_select(items: Sequence[ProviderDescriptor]) -> ProviderDescriptor | None:
    try:
        import questionary
        from questionary import Choice
    except Exception:
        return None

    selected = questionary.select(
        "Scroll or click one option. Enter confirms.",
        choices=[Choice(title=_choice_title(item), value=item) for item in items],
        style=_questionary_style(),
        pointer=">",
        qmark="",
        use_jk_keys=True,
        mouse_support=True,
    ).ask()
    if selected is None:
        raise KeyboardInterrupt
    return selected


def _questionary_style():
    from prompt_toolkit.styles import Style

    return Style(
        [
            ("qmark", "fg:#5CE1FF bold"),
            ("question", "fg:#5CE1FF bold"),
            ("pointer", "fg:#5CE1FF bold"),
            ("highlighted", "fg:#5CE1FF bold"),
            ("selected", "fg:#5CE1FF"),
            ("checkbox-selected", "fg:#5CE1FF"),
            ("answer", "fg:#5CE1FF bold"),
        ]
    )


def _choice_title(item: ProviderDescriptor) -> str:
    notes = []
    if item.default_model:
        notes.append(item.default_model)
    if item.env_var:
        notes.append(item.env_var)
    elif item.kind == "search":
        notes.append("no key required")
    suffix = f"  -  {', '.join(notes)}" if notes else ""
    return f"{item.label}{suffix}"


def _search_screen(
    items: Sequence[ProviderDescriptor],
    selected: Sequence[ProviderDescriptor],
) -> list[ProviderDescriptor]:
    while True:
        query = input("Search providers/plugins (blank shows all): ").strip().lower()
        matches = [
            item for item in items if _matches(item, query)
        ]
        if matches:
            _table(matches, selected)
            return matches
        print("No matches. Try a shorter search.")


def _matches(item: ProviderDescriptor, query: str) -> bool:
    haystack = f"{item.id} {item.label} {item.kind} {item.base_url or ''}".lower()
    return not query or query in haystack


def _table(items: Sequence[ProviderDescriptor], selected: Sequence[ProviderDescriptor]) -> None:
    print()
    print(" #  Pick  Provider                         Notes")
    print("--  ----  -------------------------------  ------------------------------")
    for index, item in enumerate(items, start=1):
        mark = "yes" if item in selected else " "
        notes = []
        if item.default_model:
            notes.append(item.default_model)
        if item.env_var:
            notes.append(item.env_var)
        elif item.kind == "search":
            notes.append("no key")
        print(f"{index:>2}  {mark:<4}  {item.label:<31}  {', '.join(notes)[:30]}")
    print()


def _parse_indexes(raw: str, count: int) -> list[int]:
    if not raw:
        raise ValueError("Enter a number, comma-list, `all`, `done`, or `skip`.")
    indexes: list[int] = []
    try:
        for chunk in raw.replace(" ", "").split(","):
            if not chunk:
                continue
            if "-" in chunk:
                start, end = chunk.split("-", 1)
                indexes.extend(range(int(start) - 1, int(end)))
            else:
                indexes.append(int(chunk) - 1)
    except ValueError as exc:
        raise ValueError("Selection must be numbers like `1`, `1,3`, or `2-4`.") from exc
    if any(index < 0 or index >= count for index in indexes):
        raise ValueError("Selection out of range.")
    return indexes


def _required(label: str, default: str | None = None) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print("Required.")


def _optional(label: str, default: str | None = None, hint: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    extra = f" ({hint})" if hint else ""
    value = input(f"{label}{suffix}{extra}: ").strip()
    return value or (default or "")


def _confirm(prompt: str, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        value = input(f"{prompt} [{suffix}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Answer yes or no.")


def _password_score(password: str) -> tuple[int, list[str]]:
    checks = [
        (len(password) >= 8, "use at least 8 characters"),
        (any(ch.islower() for ch in password), "add lowercase letters"),
        (any(ch.isupper() for ch in password), "add uppercase letters"),
        (any(ch.isdigit() for ch in password), "add a number"),
        (any(not ch.isalnum() for ch in password), "add a symbol"),
    ]
    score = sum(1 for ok, _ in checks if ok)
    notes = [message for ok, message in checks if not ok]
    return score, notes


def _secret_prompt(prompt: str) -> str:
    if sys.platform == "win32":
        return _windows_secret_prompt(prompt + ": ")
    while True:
        value = getpass.getpass(prompt + ": ").strip()
        if value:
            return value
        print("Required.")


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
            _redraw_secret(prompt, chars, visible)
            continue
        if ch in ("\b", "\x7f"):
            if chars:
                chars.pop()
                _redraw_secret(prompt, chars, visible)
            continue
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch:
            chars.append(ch)
            sys.stdout.write(ch if visible else "*")
            sys.stdout.flush()


def _redraw_secret(prompt: str, chars: Sequence[str], visible: bool) -> None:
    rendered = "".join(chars) if visible else "*" * len(chars)
    sys.stdout.write("\r" + " " * (len(prompt) + max(len(chars), 1) + 18) + "\r")
    sys.stdout.write(prompt + rendered)
    sys.stdout.flush()


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def _banner() -> None:
    print("=" * WIDTH)
    print("CITRINE SETUP".center(WIDTH))
    print("Local credentials, model providers, search, and audio plugins".center(WIDTH))
    print("=" * WIDTH)
    print()


def _section(step: str, title: str) -> None:
    print()
    print("-" * WIDTH)
    print(f"{step}  {title}")
    print("-" * WIDTH)


def _card(title: str) -> None:
    print()
    print(f"[ {title} ]")


if __name__ == "__main__":
    main()
