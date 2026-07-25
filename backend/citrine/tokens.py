"""Token accounting helpers for status and session usage."""

from __future__ import annotations

MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "gpt-5": 200_000,
    "gpt-5-mini": 200_000,
    "o3": 200_000,
    "o4-mini": 200_000,
    "gpt-4.1": 1_000_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "claude-sonnet-4-5": 200_000,
    "claude-opus-4-1": 200_000,
    "claude-sonnet-4-0": 200_000,
    "claude-3-7-sonnet-latest": 200_000,
    "claude-3-5-sonnet-latest": 200_000,
    "claude-3-5-haiku-latest": 200_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gemini-1.5-pro": 1_000_000,
    "gemini-1.5-flash": 1_000_000,
    "deepseek-r1": 128_000,
    "deepseek-reasoner": 128_000,
    "deepseek-chat": 128_000,
    "grok-4": 256_000,
    "qwen3-coder": 256_000,
    "kimi-k2": 128_000,
    "mistral-medium-3": 128_000,
    "mistral-medium-latest": 128_000,
    "mistral-large-latest": 128_000,
    "codestral-latest": 256_000,
}


def estimate_tokens(text: str) -> int:
    """Reasonable local fallback when provider usage is unavailable."""
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def context_window_for_model(model: str | None) -> int:
    if not model:
        return 0
    name = model.lower()
    for key, value in MODEL_CONTEXT_WINDOWS.items():
        if key in name:
            return value
    if "1m" in name:
        return 1_000_000
    if "256k" in name:
        return 256_000
    if "250k" in name:
        return 250_000
    if "200k" in name:
        return 200_000
    if "128k" in name:
        return 128_000
    if "32k" in name:
        return 32_000
    if "16k" in name:
        return 16_000
    return 128_000


def format_tokens(used: int, total: int) -> str:
    if total <= 0:
        return "--"
    return f"{compact_tokens(used)}/{compact_tokens(total)}"


def compact_tokens(value: int) -> str:
    if value >= 1_000_000:
        amount = value / 1_000_000
        return f"{amount:.1f}m".replace(".0m", "m")
    if value >= 1_000:
        amount = value / 1_000
        return f"{amount:.1f}k".replace(".0k", "k")
    return str(value)
