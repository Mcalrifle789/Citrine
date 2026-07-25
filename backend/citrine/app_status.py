"""Runtime status payloads for the Citrine renderer."""

from __future__ import annotations

from citrine.config import CitrineConfig


def app_status(config: CitrineConfig) -> dict[str, object]:
    provider = config.active_provider()
    agent = config.active_agent_config()
    model = agent.model or (provider.model if provider else None)
    total_tokens = token_window_for_model(model)
    return {
        "provider": provider.label if provider else "Not configured",
        "provider_id": provider.id if provider else None,
        "model": model or "No model",
        "tokens": format_tokens(total_tokens, total_tokens),
        "token_remaining": total_tokens,
        "token_total": total_tokens,
        "session": config.active_session,
        "sessions": config.sessions,
        "agent": agent.name,
        "agents": [item.name for item in config.agents],
        "providers": [
            {"id": item.id, "label": item.label, "model": item.model}
            for item in config.providers
        ],
        "models": model_suggestions(model),
    }


def token_window_for_model(model: str | None) -> int:
    if not model:
        return 0
    name = model.lower()
    if "1m" in name or "gemini-1.5-pro" in name or "gemini-2" in name:
        return 1_000_000
    if "250k" in name or "claude" in name:
        return 250_000
    if "128k" in name or "gpt-4o" in name or "deepseek" in name:
        return 128_000
    if "32k" in name:
        return 32_000
    if "16k" in name:
        return 16_000
    return 128_000


def format_tokens(remaining: int, total: int) -> str:
    if total <= 0:
        return "--"
    return f"{_compact(remaining)}/{_compact(total)}"


def model_suggestions(active_model: str | None) -> list[str]:
    suggestions = [
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "anthropic/claude-3-5-haiku-latest",
        "anthropic/claude-3-5-sonnet-latest",
        "google/gemini-1.5-flash",
        "google/gemini-1.5-pro",
        "deepseek/deepseek-chat",
        "meta-llama/llama-3.1-8b-instant",
        "mistral/mistral-small-latest",
    ]
    if active_model and active_model not in suggestions:
        return [active_model, *suggestions]
    return suggestions


def _compact(value: int) -> str:
    if value >= 1_000_000:
        return f"{value // 1_000_000}m"
    if value >= 1_000:
        return f"{value // 1_000}k"
    return str(value)
