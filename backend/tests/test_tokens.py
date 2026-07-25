from citrine.tokens import context_window_for_model, estimate_tokens, format_tokens


def test_format_tokens_uses_compact_decimal_notation():
    assert format_tokens(1_234, 128_000) == "1.2k/128k"
    assert format_tokens(45_300, 1_000_000) == "45.3k/1m"


def test_context_window_comes_from_model_metadata():
    assert context_window_for_model("openai/gpt-4o-mini") == 128_000
    assert context_window_for_model("google/gemini-2.5-pro") == 1_000_000


def test_estimate_tokens_never_returns_zero_for_text():
    assert estimate_tokens("hello") == 1
