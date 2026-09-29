"""Repository creation with Citrine credited as a contributor.

These run against real git in a temporary directory, because the thing being
verified is what actually lands in the commit object — author name, author
email, and the trailer. Mocking the subprocess would assert that the right
command was composed, which is the part that was never in doubt.

Nothing here touches the network: `create_repository` is split so the local
commit work is testable on its own, and the `gh` half is the part that is not
exercised.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from citrine.git_identity import Identity
from citrine.github import (
    SCAFFOLD_FILENAME,
    commit,
    init_repository,
    is_repository,
    status,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)

IDENTITY = Identity("Citrine Agent", "12345678+citrine@users.noreply.github.com")


def _git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(path), capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


@pytest.fixture
def workspace(tmp_path, monkeypatch) -> Path:
    """An isolated repository root.

    The user identity is forced here because git refuses to commit without
    one, and a developer machine's global config must not leak into the
    assertions.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "gitconfig-system"))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test User")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "user@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test User")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "user@example.com")
    root = tmp_path / "project"
    root.mkdir()
    return root


# ------------------------------------------------------------------- init


def test_init_creates_a_repository(workspace):
    result = init_repository(workspace, "demo", IDENTITY)
    assert result.ok
    assert is_repository(workspace)


def test_init_pins_the_branch_name(workspace):
    """Reported back to the user, so it has to be the branch that exists —
    not whatever init.defaultBranch happened to be."""
    init_repository(workspace, "demo", IDENTITY)
    assert _git(workspace, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_init_writes_the_scaffold(workspace):
    init_repository(workspace, "demo", IDENTITY)
    assert (workspace / SCAFFOLD_FILENAME).exists()
    assert (workspace / ".gitignore").exists()
    assert "demo" in (workspace / SCAFFOLD_FILENAME).read_text(encoding="utf-8")


def test_the_scaffold_commit_is_authored_by_citrine(workspace):
    """This is the commit that puts Citrine into the history, and the history
    is what GitHub computes its contributors list from."""
    init_repository(workspace, "demo", IDENTITY)
    assert _git(workspace, "log", "-1", "--format=%an") == "Citrine Agent"
    assert _git(workspace, "log", "-1", "--format=%ae") == IDENTITY.email


def test_the_scaffold_commit_also_carries_the_trailer(workspace):
    init_repository(workspace, "demo", IDENTITY)
    body = _git(workspace, "log", "-1", "--format=%B")
    assert IDENTITY.trailer in body


def test_git_parses_the_trailer(workspace):
    """The real check: git's own trailer parser has to find it. A trailer in
    the wrong place is invisible to git and to GitHub alike."""
    init_repository(workspace, "demo", IDENTITY)
    trailers = _git(
        workspace, "log", "-1", "--format=%(trailers:key=Co-Authored-By,valueonly)"
    )
    assert IDENTITY.email in trailers


def test_init_is_idempotent(workspace):
    init_repository(workspace, "demo", IDENTITY)
    before = _git(workspace, "rev-parse", "HEAD")

    second = init_repository(workspace, "demo", IDENTITY)
    assert second.ok
    assert _git(workspace, "rev-parse", "HEAD") == before


def test_init_adopts_an_existing_repository(workspace):
    """Running /init in a repository the user already has must not reinitialise
    it or lose their history."""
    _git(workspace, "init", "-b", "trunk")
    (workspace / "existing.txt").write_text("mine", encoding="utf-8")
    _git(workspace, "add", "existing.txt")
    _git(workspace, "commit", "-m", "my own work")

    result = init_repository(workspace, "demo", IDENTITY)
    assert result.ok
    assert _git(workspace, "rev-parse", "--abbrev-ref", "HEAD") == "trunk"
    assert "my own work" in _git(workspace, "log", "--format=%s")


def test_init_warns_when_the_address_cannot_be_linked(workspace):
    """Silently producing commits that will never show in the contributors
    graph is exactly the failure this feature is supposed to avoid."""
    generic = Identity("Citrine Agent", "citrine-agent@users.noreply.github.com")
    result = init_repository(workspace, "demo", generic)
    assert "CITRINE_GIT_EMAIL" in result.text()


def test_init_does_not_warn_for_a_linkable_address(workspace):
    result = init_repository(workspace, "demo", IDENTITY)
    assert "CITRINE_GIT_EMAIL" not in result.text()


# ----------------------------------------------------------------- commit


def test_commit_keeps_the_user_as_author(workspace):
    """It is the user's work. Citrine's part is recorded by the trailer,
    which is what the trailer is for."""
    init_repository(workspace, "demo", IDENTITY)
    (workspace / "feature.py").write_text("print('hi')\n", encoding="utf-8")
    _git(workspace, "add", "feature.py")

    result = commit(workspace, "feat: add the feature", IDENTITY)
    assert result.ok
    assert _git(workspace, "log", "-1", "--format=%an") == "Test User"


def test_commit_credits_citrine_as_co_author(workspace):
    init_repository(workspace, "demo", IDENTITY)
    (workspace / "feature.py").write_text("print('hi')\n", encoding="utf-8")
    _git(workspace, "add", "feature.py")
    commit(workspace, "feat: add the feature", IDENTITY)

    trailers = _git(
        workspace, "log", "-1", "--format=%(trailers:key=Co-Authored-By,valueonly)"
    )
    assert IDENTITY.email in trailers


def test_commit_refuses_when_nothing_is_staged(workspace):
    init_repository(workspace, "demo", IDENTITY)
    result = commit(workspace, "feat: nothing", IDENTITY)
    assert not result.ok
    assert "Nothing is staged" in result.text()


def test_commit_refuses_outside_a_repository(workspace):
    result = commit(workspace, "feat: thing", IDENTITY)
    assert not result.ok
    assert "not a git repository" in result.text()


def test_commit_reports_the_file_count(workspace):
    init_repository(workspace, "demo", IDENTITY)
    for name in ("a.py", "b.py"):
        (workspace / name).write_text("x\n", encoding="utf-8")
    _git(workspace, "add", "a.py", "b.py")

    assert "2 files" in commit(workspace, "feat: two", IDENTITY).text()


# ----------------------------------------------------------------- status


def test_status_reports_the_identity(workspace):
    text = status(workspace, IDENTITY).text()
    assert IDENTITY.email in text
    assert "Co-Authored-By:" in text


def test_status_explains_an_unlinkable_address(workspace):
    generic = Identity("Citrine Agent", "citrine-agent@users.noreply.github.com")
    text = status(workspace, generic).text()
    assert "contributors graph" in text
    assert "CITRINE_GIT_EMAIL" in text


def test_status_confirms_a_linkable_address(workspace):
    assert "contributors list" in status(workspace, IDENTITY).text()
