"""Chat routing for configured Citrine agents."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from citrine.catalog import provider_by_id
from citrine.config import CitrineConfig
from citrine.secrets_store import load_secret, secret_key


def send_chat(message: str, config: CitrineConfig | None = None) -> str:
    cfg = config or CitrineConfig()
    provider = cfg.active_provider()
    if provider is None:
        return (
            "No model provider is configured yet.\n"
            "Run `citrine setup`, or use /provider after setup is wired into the UI."
        )

    descriptor = provider_by_id(provider.id)
    if descriptor is None:
        return f"Unknown provider: {provider.id}"

    model = cfg.active_agent_config().model or provider.model or descriptor.default_model
    if not model:
        return f"{provider.label} is configured, but no model is selected. Use /model <name>."

    api_key = load_secret(secret_key("provider", provider.id))
    if not api_key:
        return f"{provider.label} has no stored API key. Run `citrine setup`."

    if descriptor.kind == "openai":
        return _send_openai_compatible(message, provider.label, provider.base_url or descriptor.base_url, model, api_key)

    return (
        f"{provider.label} is selected with model {model}, but this provider adapter "
        "is not implemented yet. OpenAI-compatible providers work in this slice."
    )


def _send_openai_compatible(
    message: str,
    label: str,
    base_url: str | None,
    model: str,
    api_key: str,
) -> str:
    if not base_url:
        return f"{label} needs a base URL before Citrine can call it. Run `citrine setup`."

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
        return _provider_error(label, exc.code, body)
    except urllib.error.URLError as exc:
        return f"{label} network error: {exc.reason}"
    except TimeoutError:
        return f"{label} timed out while generating a response."

    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError):
        return f"{label} returned an unexpected response: {json.dumps(data)[:500]}"


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
