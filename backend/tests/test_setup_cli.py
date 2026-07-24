import pytest

from citrine.setup_cli import _parse_indexes, _password_score


def test_parse_indexes_accepts_commas_and_ranges():
    assert _parse_indexes("1,3-4", 5) == [0, 2, 3]


def test_parse_indexes_rejects_words_cleanly():
    with pytest.raises(ValueError, match="Selection must be numbers"):
        _parse_indexes("openai", 3)


def test_password_score_rewards_length_and_character_classes():
    score, notes = _password_score("Citrine!42")
    assert score == 5
    assert notes == []


def test_password_score_explains_weak_passwords():
    score, notes = _password_score("short")
    assert score < 3
    assert "use at least 8 characters" in notes
