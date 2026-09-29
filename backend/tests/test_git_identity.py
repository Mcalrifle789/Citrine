"""Citrine's commit identity and the co-author trailer.

This is the whole mechanism behind "show Citrine as a contributor on GitHub":
GitHub builds its contributor list from commit authorship, and the trailer is
the documented way to credit a second identity on someone else's commit. If the
trailer is malformed, or sits in the wrong place in the message, git and GitHub
both ignore it silently — so the formatting is worth pinning down.
"""

import pytest

from citrine.git_identity import (
    DEFAULT_EMAIL,
    DEFAULT_NAME,
    EMAIL_ENV,
    NAME_ENV,
    Identity,
    add_coauthor_trailer,
    citrine_identity,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv(NAME_ENV, raising=False)
    monkeypatch.delenv(EMAIL_ENV, raising=False)


# ------------------------------------------------------------------ identity


def test_defaults_to_the_citrine_agent():
    identity = citrine_identity()
    assert identity.name == DEFAULT_NAME
    assert identity.email == DEFAULT_EMAIL


def test_the_identity_is_configurable(monkeypatch):
    monkeypatch.setenv(NAME_ENV, "Citrine")
    monkeypatch.setenv(EMAIL_ENV, "123+citrine@users.noreply.github.com")
    identity = citrine_identity()
    assert identity.name == "Citrine"
    assert identity.email == "123+citrine@users.noreply.github.com"


def test_a_malformed_email_falls_back_to_the_default(monkeypatch):
    """git accepts almost anything as an author, so a typo would otherwise
    produce commits credited to a nonexistent address."""
    monkeypatch.setenv(EMAIL_ENV, "not-an-email")
    assert citrine_identity().email == DEFAULT_EMAIL


def test_an_empty_name_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv(NAME_ENV, "   ")
    assert citrine_identity().name == DEFAULT_NAME


def test_a_name_cannot_forge_a_second_trailer_line(monkeypatch):
    """The trailer is `Name <email>` on one line. A newline in the name would
    let a configured value inject an extra trailer of its choosing."""
    monkeypatch.setenv(NAME_ENV, "Evil\nCo-Authored-By: Someone <x@y.z>")
    assert "\n" not in citrine_identity().name


def test_a_name_cannot_break_the_angle_bracket_form(monkeypatch):
    monkeypatch.setenv(NAME_ENV, "Bad <injected@example.com>")
    name = citrine_identity().name
    assert "<" not in name and ">" not in name


def test_the_string_form_is_what_git_expects():
    identity = Identity("Citrine Agent", "citrine@example.com")
    assert str(identity) == "Citrine Agent <citrine@example.com>"


def test_the_trailer_is_the_key_github_parses():
    identity = Identity("Citrine Agent", "citrine@example.com")
    assert identity.trailer == "Co-Authored-By: Citrine Agent <citrine@example.com>"


# ------------------------------------------------- account linkability


def test_a_generic_noreply_address_cannot_be_linked():
    """It renders as a co-author but joins no contributors graph, and saying
    so is the difference between the feature working and appearing to."""
    assert not Identity("Citrine", DEFAULT_EMAIL).links_to_account


def test_a_numbered_noreply_address_links_to_its_account():
    identity = Identity("Citrine", "12345678+citrine@users.noreply.github.com")
    assert identity.links_to_account


def test_an_ordinary_address_is_assumed_linkable():
    assert Identity("Citrine", "citrine@example.com").links_to_account


# ---------------------------------------------------------- author override


def test_the_identity_is_applied_through_the_environment():
    """Set through env rather than `git config` so Citrine never rewrites who
    the user commits as in their own repository."""
    env = Identity("Citrine Agent", "citrine@example.com").env()
    assert env["GIT_AUTHOR_NAME"] == "Citrine Agent"
    assert env["GIT_AUTHOR_EMAIL"] == "citrine@example.com"
    assert env["GIT_COMMITTER_EMAIL"] == "citrine@example.com"


# ------------------------------------------------------------- the trailer


def test_the_trailer_is_appended():
    message = add_coauthor_trailer("feat: add a thing")
    assert message.splitlines()[-1].startswith("Co-Authored-By:")


def test_the_trailer_gets_its_own_paragraph():
    """git only parses a trailer block separated from the body by a blank
    line; without it GitHub shows the line as ordinary message text."""
    lines = add_coauthor_trailer("feat: add a thing").splitlines()
    assert lines[1] == ""


def test_it_joins_an_existing_trailer_block():
    """A blank line inside the block would end it, orphaning what follows."""
    message = add_coauthor_trailer(
        "fix: repair it\n\nSigned-off-by: Mike <mike@example.com>"
    )
    lines = message.splitlines()
    assert lines[-2].startswith("Signed-off-by:")
    assert lines[-1].startswith("Co-Authored-By:")


def test_it_is_idempotent():
    """Amending a commit must not stack duplicate trailers."""
    once = add_coauthor_trailer("feat: thing")
    assert add_coauthor_trailer(once) == once


def test_the_body_survives():
    message = add_coauthor_trailer("feat: thing\n\nWith an explanation.")
    assert "With an explanation." in message


def test_a_custom_identity_is_used():
    identity = Identity("Someone Else", "else@example.com")
    assert "else@example.com" in add_coauthor_trailer("feat: x", identity)
