import logging

from citrine.logging import get_logger, redact


def test_redacts_openai_style_keys():
    assert "sk-abcdef0123456789abcdef" not in redact("key is sk-abcdef0123456789abcdef here")


def test_redaction_leaves_a_marker():
    assert "[REDACTED]" in redact("key is sk-abcdef0123456789abcdef here")


def test_redacts_anthropic_style_keys():
    assert "sk-ant-" not in redact("sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaa")


def test_redacts_bearer_tokens():
    assert "deadbeefdeadbeefdeadbeef" not in redact("Authorization: Bearer deadbeefdeadbeefdeadbeef")


def test_redacts_json_token_fields():
    assert "hunter2hunter2hunter2" not in redact('{"token": "hunter2hunter2hunter2"}')


def test_leaves_ordinary_text_alone():
    assert redact("connected on port 54321") == "connected on port 54321"


def test_logger_output_is_redacted(caplog):
    """Redaction happens at the logger, so no call site can forget it."""
    logger = get_logger("citrine.test")
    with caplog.at_level(logging.INFO):
        logger.info("saving sk-abcdef0123456789abcdef")
    assert "sk-abcdef0123456789abcdef" not in caplog.text
