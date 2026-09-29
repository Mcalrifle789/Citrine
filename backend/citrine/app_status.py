"""Runtime status payloads for the Citrine renderer."""

from __future__ import annotations

from citrine.catalog import GENERAL_MODEL_SUGGESTIONS, MODEL_SUGGESTIONS
from citrine.config import CitrineConfig
from citrine.tokens import context_window_for_model, format_tokens


def app_status(config: CitrineConfig) -> dict[str, object]:
    provider = config.active_provider()
    agent = config.active_agent_config()
    model = agent.model or (provider.model if provider else None)
    total_tokens = context_window_for_model(model)
    # Per agent *and* session: switching agents switches model, and a count
    # measured against a different context window is a different number.
    used_tokens = config.session_tokens()
    return {
        "provider": provider.label if provider else "Not configured",
        "provider_id": provider.id if provider else None,
        "model": model or "No model",
        "tokens": format_tokens(used_tokens, total_tokens),
        "token_used": used_tokens,
        "token_total": total_tokens,
        "session": config.active_session,
        "sessions": config.sessions,
        # The renderer keys its scrollback on this and blanks the window when it
        # changes, which is what makes /new, /session, /agent and /reset start a
        # visibly fresh conversation.
        "transcript_key": config.transcript_key(),
        "agent": agent.name,
        "agents": [item.name for item in config.agents],
        "providers": [
            {"id": item.id, "label": item.label, "model": item.model}
            for item in config.providers
        ],
        "models": model_suggestions(model, provider.id if provider else None),
    }


def model_suggestions(active_model: str | None, provider_id: str | None = None) -> list[str]:
    suggestions = list(
        MODEL_SUGGESTIONS.get(provider_id or "", GENERAL_MODEL_SUGGESTIONS)
    )
    if active_model and active_model not in suggestions:
        return [active_model, *suggestions]
    return suggestions
