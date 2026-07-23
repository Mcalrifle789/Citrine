import os
from pathlib import Path

import pytest

from citrine import paths


def test_citrine_home_defaults_under_user_home(monkeypatch):
    monkeypatch.delenv("CITRINE_HOME", raising=False)
    assert paths.citrine_home() == Path.home() / ".citrine"


def test_citrine_home_respects_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path))
    assert paths.citrine_home() == tmp_path


def test_derived_paths_live_under_citrine_home(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path))
    assert paths.config_path() == tmp_path / "config.json"
    assert paths.logs_dir() == tmp_path / "logs"
    assert paths.sessions_db_path() == tmp_path / "sessions.sqlite3"


def test_all_paths_are_absolute(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path))
    for p in (paths.citrine_home(), paths.config_path(), paths.logs_dir(),
              paths.documents_dir(), paths.agents_dir()):
        assert p.is_absolute(), f"{p} is not absolute"


def test_agents_dir_lives_under_documents(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_DOCUMENTS", str(tmp_path))
    assert paths.agents_dir() == tmp_path / "Citrine" / "Agents"


def test_documents_dir_respects_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_DOCUMENTS", str(tmp_path))
    assert paths.documents_dir() == tmp_path


@pytest.mark.skipif(os.name != "nt", reason="Windows shell-folder redirection")
def test_documents_dir_follows_windows_redirection(monkeypatch):
    """Documents is frequently redirected to OneDrive; the naive
    home/Documents guess is wrong on such machines."""
    monkeypatch.delenv("CITRINE_DOCUMENTS", raising=False)
    resolved = paths.documents_dir()
    assert resolved.name.lower() == "documents"


def test_ensure_dirs_creates_missing_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("CITRINE_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CITRINE_DOCUMENTS", str(tmp_path / "docs"))
    paths.ensure_dirs()
    assert (tmp_path / "home" / "logs").is_dir()
    assert (tmp_path / "docs" / "Citrine" / "Agents").is_dir()
