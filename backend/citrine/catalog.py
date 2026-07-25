"""Provider catalogs shared by setup, commands, and chat routing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    label: str
    kind: str
    base_url: str | None = None
    default_model: str | None = None
    env_var: str | None = None


CHAT_PROVIDERS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1", "anthropic/claude-sonnet-4.5", "CITRINE_OPENROUTER_API_KEY"),
    ProviderDescriptor("opencode", "Opencode", "openai", None, None, "CITRINE_OPENCODE_API_KEY"),
    ProviderDescriptor("kilo", "Kilo", "openai", None, None, "CITRINE_KILO_API_KEY"),
    ProviderDescriptor("litellm", "LiteLLM", "openai", "http://127.0.0.1:4000/v1", None, "CITRINE_LITELLM_API_KEY"),
    ProviderDescriptor("gemini", "Google Gemini", "gemini", None, "gemini-2.5-pro", "CITRINE_GEMINI_API_KEY"),
    ProviderDescriptor("openai", "OpenAI", "openai", "https://api.openai.com/v1", "gpt-5", "CITRINE_OPENAI_API_KEY"),
    ProviderDescriptor("anthropic", "Anthropic", "anthropic", None, "claude-sonnet-4-5", "CITRINE_ANTHROPIC_API_KEY"),
    ProviderDescriptor("mistral", "Mistral AI", "openai", "https://api.mistral.ai/v1", "mistral-medium-latest", "CITRINE_MISTRAL_API_KEY"),
    ProviderDescriptor("deepseek", "DeepSeek", "openai", "https://api.deepseek.com/v1", "deepseek-reasoner", "CITRINE_DEEPSEEK_API_KEY"),
    ProviderDescriptor("groq", "Groq", "openai", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "CITRINE_GROQ_API_KEY"),
    ProviderDescriptor("together", "Together AI", "openai", "https://api.together.xyz/v1", None, "CITRINE_TOGETHER_API_KEY"),
    ProviderDescriptor("fireworks", "Fireworks AI", "openai", "https://api.fireworks.ai/inference/v1", None, "CITRINE_FIREWORKS_API_KEY"),
    ProviderDescriptor("deepinfra", "DeepInfra", "openai", "https://api.deepinfra.com/v1/openai", None, "CITRINE_DEEPINFRA_API_KEY"),
    ProviderDescriptor("novita", "Novita", "openai", "https://api.novita.ai/v3/openai", None, "CITRINE_NOVITA_API_KEY"),
    ProviderDescriptor("custom", "Custom OpenAI-compatible provider", "openai", None, None, "CITRINE_CUSTOM_API_KEY"),
)

MODEL_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "openrouter": (
        "anthropic/claude-sonnet-4.5",
        "anthropic/claude-opus-4.1",
        "openai/gpt-5",
        "google/gemini-2.5-pro",
        "x-ai/grok-4",
        "deepseek/deepseek-r1",
        "qwen/qwen3-coder",
        "moonshotai/kimi-k2",
        "mistralai/mistral-medium-3",
        "openai/gpt-4o",
    ),
    "openai": (
        "gpt-5",
        "gpt-5-mini",
        "o3",
        "o4-mini",
        "gpt-4.1",
        "gpt-4o",
        "gpt-4o-mini",
    ),
    "anthropic": (
        "claude-sonnet-4-5",
        "claude-opus-4-1",
        "claude-sonnet-4-0",
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    ),
    "gemini": (
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ),
    "deepseek": (
        "deepseek-reasoner",
        "deepseek-chat",
        "deepseek-coder",
    ),
    "mistral": (
        "mistral-medium-latest",
        "mistral-large-latest",
        "codestral-latest",
        "mistral-small-latest",
    ),
    "groq": (
        "openai/gpt-oss-120b",
        "qwen/qwen3-32b",
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        "llama-3.3-70b-versatile",
    ),
    "litellm": (
        "gpt-5",
        "claude-sonnet-4-5",
        "gemini-2.5-pro",
        "deepseek-reasoner",
        "qwen3-coder",
    ),
    "custom": (
        "gpt-5",
        "claude-sonnet-4-5",
        "gemini-2.5-pro",
        "deepseek-reasoner",
        "qwen3-coder",
    ),
    "opencode": (
        "gpt-5",
        "claude-sonnet-4-5",
        "gemini-2.5-pro",
        "deepseek-reasoner",
        "qwen3-coder",
    ),
    "kilo": (
        "gpt-5",
        "claude-sonnet-4-5",
        "gemini-2.5-pro",
        "deepseek-reasoner",
        "qwen3-coder",
    ),
}

GENERAL_MODEL_SUGGESTIONS: tuple[str, ...] = (
    "openai/gpt-5",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-opus-4.1",
    "google/gemini-2.5-pro",
    "x-ai/grok-4",
    "deepseek/deepseek-r1",
    "qwen/qwen3-coder",
    "moonshotai/kimi-k2",
    "mistralai/mistral-medium-3",
    "openai/o3",
    "openai/gpt-4.1",
    "openai/gpt-4o",
)

SEARCH_PROVIDERS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor("firecrawl", "Firecrawl", "search", None, None, "CITRINE_FIRECRAWL_API_KEY"),
    ProviderDescriptor("duckduckgo", "DuckDuckGo", "search", None, None, None),
    ProviderDescriptor("parallel", "Parallel", "search", None, None, "CITRINE_PARALLEL_API_KEY"),
    ProviderDescriptor("parallel-free", "Parallel Free", "search", None, None, None),
    ProviderDescriptor("brave", "Brave Search", "search", None, None, "CITRINE_BRAVE_API_KEY"),
    ProviderDescriptor("google", "Google Search", "search", None, None, "CITRINE_GOOGLE_SEARCH_API_KEY"),
    ProviderDescriptor("perplexity", "Perplexity", "search", None, None, "CITRINE_PERPLEXITY_API_KEY"),
    ProviderDescriptor("gemini-search", "Google Gemini Search", "search", None, None, "CITRINE_GEMINI_API_KEY"),
    ProviderDescriptor("custom-search", "Custom search provider", "search", None, None, "CITRINE_CUSTOM_SEARCH_API_KEY"),
)

MUSIC_PLUGINS: tuple[ProviderDescriptor, ...] = (
    ProviderDescriptor("elevenlabs", "ElevenLabs", "music", None, None, "CITRINE_ELEVENLABS_API_KEY"),
    ProviderDescriptor("deepgram", "Deepgram", "music", None, None, "CITRINE_DEEPGRAM_API_KEY"),
    ProviderDescriptor("suno", "SUNO", "music", None, None, "CITRINE_SUNO_API_KEY"),
    ProviderDescriptor("spotify", "Spotify", "music", None, None, "CITRINE_SPOTIFY_API_KEY"),
    ProviderDescriptor("custom-mcp", "Custom MCP music/audio plugin", "music", None, None, "CITRINE_CUSTOM_MCP_API_KEY"),
)


def provider_by_id(provider_id: str) -> ProviderDescriptor | None:
    return _find(CHAT_PROVIDERS, provider_id)


def search_provider_by_id(provider_id: str) -> ProviderDescriptor | None:
    return _find(SEARCH_PROVIDERS, provider_id)


def music_plugin_by_id(plugin_id: str) -> ProviderDescriptor | None:
    return _find(MUSIC_PLUGINS, plugin_id)


def _find(items: tuple[ProviderDescriptor, ...], item_id: str) -> ProviderDescriptor | None:
    normalized = item_id.strip().lower()
    for item in items:
        if item.id == normalized:
            return item
    return None
