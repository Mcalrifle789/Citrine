"""Chat routing for configured Citrine agents."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from citrine.catalog import provider_by_id
from citrine.config import CitrineConfig
from citrine.secrets_store import load_secret, secret_key
from citrine.tokens import estimate_tokens


@dataclass(frozen=True)
class ChatResult:
    text: str
    tokens_used: int


def send_chat(message: str, config: CitrineConfig | None = None) -> ChatResult:
    cfg = config or CitrineConfig()
    provider = cfg.active_provider()
    if provider is None:
        text = (
            "No model provider is configured yet.\n"
            "Run `citrine setup`, or use /provider after setup is wired into the UI."
        )
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))

    descriptor = provider_by_id(provider.id)
    if descriptor is None:
        text = f"Unknown provider: {provider.id}"
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))

    model = cfg.active_agent_config().model or provider.model or descriptor.default_model
    if not model:
        text = f"{provider.label} is configured, but no model is selected. Use /model <name>."
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))

    api_key = _api_key(provider.id, descriptor.env_var)
    if not api_key:
        text = f"{provider.label} has no stored API key. Run `citrine setup`."
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))

    if descriptor.kind == "openai":
        return _send_openai_compatible(message, provider.label, provider.base_url or descriptor.base_url, model, api_key)

    text = (
        f"{provider.label} is selected with model {model}, but this provider adapter "
        "is not implemented yet. OpenAI-compatible providers work in this slice."
    )
    return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))


def _send_openai_compatible(
    message: str,
    label: str,
    base_url: str | None,
    model: str,
    api_key: str,
) -> ChatResult:
    if not base_url:
        text = f"{label} needs a base URL before Citrine can call it. Run `citrine setup`."
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))

    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are Citrine, a local-first personal terminal agent.",
            },
            {"role": "user", "content": message},
        ],
        "temperature": 0.7,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Mcalrifle789/Citrine",
            "X-Title": "Citrine",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        text = _provider_error(label, exc.code, body)
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))
    except urllib.error.URLError as exc:
        text = f"{label} network error: {exc.reason}"
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))
    except TimeoutError:
        text = f"{label} timed out while generating a response."
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))

    try:
        text = str(data["choices"][0]["message"]["content"]).strip()
        usage = data.get("usage", {})
        total_tokens = usage.get("total_tokens")
        if isinstance(total_tokens, int) and total_tokens > 0:
            return ChatResult(text, total_tokens)
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))
    except (KeyError, IndexError, TypeError):
        text = f"{label} returned an unexpected response: {json.dumps(data)[:500]}"
        return ChatResult(text, estimate_tokens(message) + estimate_tokens(text))


def _provider_error(label: str, status: int, body: str) -> str:
    lower = body.lower()
    if any(term in lower for term in ("quota", "credit", "insufficient", "billing")):
        reason = "credits, quota, or billing"
    elif status in {401, 403}:
        reason = "authentication"
    elif status == 429:
        reason = "rate limit"
    else:
        reason = "provider"
    return f"{label} {reason} error ({status}): {body[:700]}"


def _api_key(provider_id: str, env_var: str | None) -> str | None:
    if env_var:
        import os

        value = os.environ.get(env_var)
        if value:
            return value
    return load_secret(secret_key("provider", provider_id))
