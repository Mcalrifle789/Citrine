import json
from pathlib import Path

import pytest

from citrine.protocol import ErrorCode, MessageType, parse_envelope

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "protocol"
FIXTURE_FILES = sorted(FIXTURES.glob("*.json"))


def test_fixture_directory_is_populated():
    assert len(FIXTURE_FILES) == 7


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_every_fixture_parses(path: Path):
    envelope = parse_envelope(path.read_text(encoding="utf-8"))
    assert envelope.id
    assert isinstance(envelope.type, MessageType)


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.stem)
def test_every_fixture_round_trips_without_loss(path: Path):
    original = json.loads(path.read_text(encoding="utf-8"))
    envelope = parse_envelope(path.read_text(encoding="utf-8"))
    assert json.loads(envelope.to_json()) == original


def test_error_codes_cover_the_spec_taxonomy():
    expected = {"auth", "rate_limit", "quota", "network",
                "model_not_found", "context_length", "server"}
    assert {c.value for c in ErrorCode} == expected


def test_unknown_message_type_is_rejected():
    with pytest.raises(ValueError):
        parse_envelope('{"id":"x","type":"telepathy","method":"echo","params":{}}')


def test_missing_id_is_rejected():
    with pytest.raises(ValueError):
        parse_envelope('{"type":"request","method":"echo","params":{}}')


def test_malformed_json_is_rejected():
    with pytest.raises(ValueError):
        parse_envelope("{not json")
