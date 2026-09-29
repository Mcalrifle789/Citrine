"""Creating GitHub repositories with Citrine credited as a contributor.

The requirement is that a repository Citrine creates shows Citrine among the
contributors on GitHub. GitHub builds that list from commit authorship, so the
work happens in the commits:

* The scaffold commit is **authored by Citrine**. Citrine genuinely wrote those
  files, and it is this commit that puts the identity in the repository's
  history, which is what the contributors list reads.
* Every later commit Citrine makes on the user's behalf carries a
  ``Co-Authored-By:`` trailer, leaving the user as author of their own work.

See git_identity.py for why the email decides whether this actually lands.

``gh`` is used for the remote side rather than the REST API because it already
holds the user's credentials. Citrine asking for a token it would then have to
store, when the official CLI has one, is a worse trade for the user.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from citrine.git_identity import Identity, add_coauthor_trailer, citrine_identity

SCAFFOLD_FILENAME = "CITRINE.md"

SCAFFOLD_TEMPLATE = """# {name}

Created with [Citrine](https://github.com/Mcalrifle789/Citrine), a local-first
personal AI terminal agent.

## About this repository

This scaffold commit was authored by the Citrine agent. Subsequent commits
Citrine helps with are authored by you and carry a `Co-Authored-By:` trailer
crediting the agent, so the history records who did what.
"""

GITIGNORE_TEMPLATE = """# Secrets
.env
.env.local
*.pem

# Dependencies
node_modules/
__pycache__/
.venv/

# Build output
dist/
build/
out/

# Editor / OS
.DS_Store
Thumbs.db
.idea/
.vscode/
"""


@dataclass
class RepoResult:
    """The outcome of a repository operation, as shown to the user."""

    ok: bool
    lines: list[str] = field(default_factory=list)

    def text(self) -> str:
        return "\n".join(self.lines)


class GitError(RuntimeError):
    """A git or gh invocation failed."""


def _run(
    args: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> str:
    """Run a command, raising GitError with its stderr on failure."""
    merged = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            args,
            cwd=str(cwd),
            env=merged,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError(f"{args[0]} is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"{' '.join(args[:2])} timed out after {timeout}s") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(f"{' '.join(args[:3])} failed: {detail[:500]}")
    return result.stdout


def has_git() -> bool:
    return shutil.which("git") is not None


def has_gh() -> bool:
    return shutil.which("gh") is not None


def gh_authenticated() -> bool:
    """Whether `gh` holds usable credentials."""
    if not has_gh():
        return False
    try:
        _run(["gh", "auth", "status"], cwd=Path.cwd(), timeout=30)
    except GitError:
        return False
    return True


def is_repository(path: Path) -> bool:
    return (path / ".git").exists()


def init_repository(
    path: Path,
    name: str | None = None,
    identity: Identity | None = None,
) -> RepoResult:
    """Initialise a git repository with a Citrine-authored scaffold commit.

    Local only — no network, no remote. This is the half that creates the
    authorship record; ``create_repository`` adds the GitHub side on top.
    """
    who = identity or citrine_identity()
    project = name or path.name
    lines: list[str] = []

    if not has_git():
        return RepoResult(False, ["git is not installed, or is not on PATH."])

    path.mkdir(parents=True, exist_ok=True)

    if is_repository(path):
        lines.append(f"{path} is already a git repository; leaving it alone.")
    else:
        # Pin the branch name rather than inheriting init.defaultBranch, so the
        # name Citrine reports back is the name that actually exists.
        _run(["git", "init", "-b", "main"], cwd=path)
        lines.append(f"Initialized an empty repository in {path} on branch main.")

    scaffold = path / SCAFFOLD_FILENAME
    wrote_any = False
    if not scaffold.exists():
        scaffold.write_text(SCAFFOLD_TEMPLATE.format(name=project), encoding="utf-8")
        wrote_any = True

    gitignore = path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE_TEMPLATE, encoding="utf-8")
        wrote_any = True

    if not wrote_any:
        lines.append("Scaffold files already present; nothing to commit.")
        return RepoResult(True, lines)

    _run(["git", "add", SCAFFOLD_FILENAME, ".gitignore"], cwd=path)

    message = add_coauthor_trailer(
        f"chore: scaffold {project} with Citrine\n\n"
        "Adds the project README and a starting .gitignore.",
        who,
    )

    # Authored *as* Citrine: this is the commit that puts the identity into the
    # history, which is what GitHub's contributors list is computed from. The
    # identity is passed through the environment so nothing is written into the
    # user's git config.
    _run(["git", "commit", "-m", message], cwd=path, env=who.env())

    lines.append(f"Committed the scaffold as {who}.")
    if not who.links_to_account:
        lines.append(
            f"Note: {who.email} is a generic address, so GitHub will show "
            "Citrine on the commit but cannot link it to an account in the "
            "contributors graph. Set CITRINE_GIT_EMAIL to the GitHub noreply "
            "address of the account you want credited "
            "(e.g. 12345678+citrine@users.noreply.github.com)."
        )
    return RepoResult(True, lines)


def create_repository(
    path: Path,
    name: str | None = None,
    private: bool = True,
    identity: Identity | None = None,
) -> RepoResult:
    """Create the repository on GitHub and push it, Citrine credited.

    The local scaffold is made first and unconditionally. If the remote step
    fails — no `gh`, not logged in, name taken — the user still has a working
    local repository with the authorship already in place, and only needs to
    add a remote.
    """
    who = identity or citrine_identity()
    project = name or path.name

    local = init_repository(path, project, who)
    lines = list(local.lines)
    if not local.ok:
        return RepoResult(False, lines)

    if not has_gh():
        lines.append("")
        lines.append(
            "The GitHub CLI (gh) is not installed, so the remote was not "
            "created. Install it from https://cli.github.com, then run:"
        )
        lines.append(f"  gh repo create {project} --source . --push")
        return RepoResult(True, lines)

    if not gh_authenticated():
        lines.append("")
        lines.append("gh is installed but not logged in. Run `gh auth login`, then:")
        lines.append(f"  gh repo create {project} --source . --push")
        return RepoResult(True, lines)

    visibility = "--private" if private else "--public"
    try:
        _run(
            ["gh", "repo", "create", project, "--source", ".", visibility, "--push"],
            cwd=path,
            timeout=180,
        )
    except GitError as error:
        lines.append("")
        lines.append(f"Creating the GitHub repository failed: {error}")
        lines.append("The local repository and its commit are intact.")
        return RepoResult(False, lines)

    lines.append("")
    lines.append(f"Created and pushed the GitHub repository {project} ({visibility[2:]}).")
    lines.append(
        f"{who.name} is recorded as the author of the scaffold commit and will "
        "be co-author on commits Citrine helps with from here."
    )
    return RepoResult(True, lines)


def commit(
    path: Path,
    message: str,
    identity: Identity | None = None,
) -> RepoResult:
    """Commit staged changes as the user, crediting Citrine as co-author.

    The user stays the author — it is their work. Citrine's contribution is
    recorded with the trailer, which is exactly what the trailer is for.
    """
    who = identity or citrine_identity()

    if not has_git():
        return RepoResult(False, ["git is not installed, or is not on PATH."])
    if not is_repository(path):
        return RepoResult(False, [f"{path} is not a git repository. Try /init first."])

    try:
        staged = _run(["git", "diff", "--cached", "--name-only"], cwd=path).strip()
    except GitError as error:
        return RepoResult(False, [str(error)])

    if not staged:
        return RepoResult(
            False,
            ["Nothing is staged. Stage the changes you want committed, then try again."],
        )

    try:
        _run(["git", "commit", "-m", add_coauthor_trailer(message, who)], cwd=path)
    except GitError as error:
        return RepoResult(False, [str(error)])

    count = len(staged.splitlines())
    noun = "file" if count == 1 else "files"
    return RepoResult(
        True,
        [f"Committed {count} {noun}, co-authored by {who}."],
    )


def status(path: Path, identity: Identity | None = None) -> RepoResult:
    """Report how Citrine's attribution is currently set up."""
    who = identity or citrine_identity()
    lines = [
        "Citrine GitHub attribution",
        f"Identity: {who}",
        f"Trailer:  {who.trailer}",
        "",
        f"git installed: {'yes' if has_git() else 'no'}",
        f"gh installed:  {'yes' if has_gh() else 'no'}",
        f"gh logged in:  {'yes' if gh_authenticated() else 'no'}",
        f"{path} is a repository: {'yes' if is_repository(path) else 'no'}",
        "",
    ]

    if who.links_to_account:
        lines.append(
            "This address can be resolved by GitHub, so Citrine will appear in "
            "the contributors list of repositories it commits to."
        )
    else:
        lines.append(
            "This is a generic address. Citrine will be shown as co-author on "
            "each commit, but GitHub cannot link it to an account, so it will "
            "not appear in the contributors graph."
        )
        lines.append(
            "To fix: create a GitHub account for the agent, then set "
            "CITRINE_GIT_EMAIL to its noreply address "
            "(Settings -> Emails -> 'Keep my email address private')."
        )
    return RepoResult(True, lines)
