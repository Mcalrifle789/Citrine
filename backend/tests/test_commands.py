"""The slash command registry.

The "/" menu in the renderer is built from COMMANDS, so anything in that tuple
is offered to the user and has to lead somewhere. The commands that write to
disk get the most attention here: they are the ones where getting it wrong
costs the user something they cannot undo with a keystroke.
"""

from pathlib import Path

import pytest

from citrine.commands import COMMANDS, COMMAND_INDEX, run_command
from citrine.config import CitrineConfig


@pytest.fixture(autouse=True)
def scratch(tmp_path, monkeypatch) -> Path:
    """Commands resolve paths against the working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ---------------------------------------------------------------- registry


def test_the_registry_has_no_duplicates():
    """A duplicate silently shadows its twin in COMMAND_INDEX."""
    names = [command.name for command in COMMANDS]
    assert len(names) == len(set(names))


def test_every_command_is_indexed():
    assert len(COMMAND_INDEX) == len(COMMANDS)


def test_every_command_describes_itself():
    """The description is the menu's hint column."""
    for command in COMMANDS:
        assert command.description, command.name


def test_plain_text_is_not_a_command():
    assert run_command("hello there") == "hello there"


def test_unknown_commands_point_at_the_catalog():
    assert "/commands" in run_command("/nope")


# -------------------------------------------------------------------- init


def test_a_bare_init_only_explains_itself(scratch):
    """It would otherwise run `git init` in whatever directory the backend
    was started in — a directory the user has no reason to know about."""
    output = run_command("/init")
    assert "Usage" in output
    assert not (scratch / ".git").exists()


def test_a_bare_init_names_the_directory_at_risk(scratch):
    """If the user is going to type `/init here`, they should be able to see
    where 'here' is first."""
    assert str(scratch) in run_command("/init")


def test_init_with_a_name_creates_a_subdirectory(scratch):
    run_command("/init demo")
    assert (scratch / "demo" / ".git").exists()
    assert (scratch / "demo" / "CITRINE.md").exists()


def test_init_here_is_the_explicit_opt_in(scratch):
    run_command("/init here")
    assert (scratch / ".git").exists()


def test_init_suggests_how_to_publish(scratch):
    assert "/github create demo" in run_command("/init demo")


# ------------------------------------------------------------------ github


def test_github_defaults_to_status(scratch):
    output = run_command("/github")
    assert "Citrine GitHub attribution" in output


def test_github_status_shows_the_trailer(scratch):
    assert "Co-Authored-By:" in run_command("/github status")


def test_github_rejects_an_unknown_action(scratch):
    output = run_command("/github frobnicate")
    assert "Unknown /github action" in output
    assert "/github create" in output


def test_github_create_needs_a_name(scratch):
    """Without one there is no way to know what to create, and guessing from
    the working directory is how you publish the wrong folder."""
    assert "Usage" in run_command("/github create")
    assert not (scratch / ".git").exists()


# ------------------------------------------------------------------ commit


def test_commit_without_a_message_explains_itself(scratch):
    output = run_command("/commit")
    assert "Usage" in output
    assert "co-author" in output


def test_commit_outside_a_repository_says_so(scratch):
    assert "not a git repository" in run_command("/commit feat: thing")


# ------------------------------------------------------- existing behaviour


def test_theme_switches_and_persists_to_config():
    config = CitrineConfig()
    assert "matrix" in run_command("/theme matrix", config)
    assert config.theme == "matrix"


def test_an_unknown_theme_is_rejected():
    config = CitrineConfig()
    run_command("/theme neon", config)
    assert config.theme == "citrine"


def test_the_catalog_lists_every_command():
    output = run_command("/commands")
    for command in COMMANDS:
        assert f"/{command.name}" in output
