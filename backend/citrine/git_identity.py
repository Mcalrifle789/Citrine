"""The commit identity Citrine signs its work with.

Why this exists
---------------

GitHub does not have a concept of "an agent that helped". Its contributor
list, and the contributions graph on a profile, are built from *commits* — and
a commit counts for an account only if its author or co-author email is one
GitHub can resolve to that account.

So making Citrine show up as a contributor is not a UI change or an API call.
It is a commit-authorship question, and there are exactly two levers:

1. ``Co-Authored-By:`` trailers. GitHub parses these and credits the named
   identity alongside the main author. This is the lever that matters, because
   the user stays the author of their own work.
2. Authoring a commit outright as Citrine. Used for the one commit Citrine
   genuinely wrote on its own — the project scaffold.

Both resolve through the email. An address GitHub cannot match still shows in
the commit's co-author list, but does not join the contributors graph, so the
address is configurable and defaults to the ``users.noreply.github.com`` form,
which is what GitHub itself hands out for exactly this purpose.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

DEFAULT_NAME = "Citrine Agent"

# The noreply form is what GitHub issues for privacy-protected commits, and it
# is the one address shape guaranteed to resolve to an account when the account
# exists. Without a numeric user id prefix it will not link to a *specific*
# account, which is why CITRINE_GIT_EMAIL exists and why /github status says so.
DEFAULT_EMAIL = "citrine-agent@users.noreply.github.com"

NAME_ENV = "CITRINE_GIT_NAME"
EMAIL_ENV = "CITRINE_GIT_EMAIL"

_EMAIL_PATTERN = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")

# GitHub links a noreply address to an account when it carries the account's
# numeric id, e.g. 12345678+octocat@users.noreply.github.com.
_LINKABLE_NOREPLY = re.compile(r"^\d+\+[^@\s]+@users\.noreply\.github\.com$")


@dataclass(frozen=True)
class Identity:
    """A git author identity."""

    name: str
    email: str

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"

    @property
    def trailer(self) -> str:
        """The ``Co-Authored-By:`` line GitHub parses."""
        return f"Co-Authored-By: {self.name} <{self.email}>"

    @property
    def links_to_account(self) -> bool:
        """Whether GitHub can resolve this address to a specific account.

        A generic noreply address is valid and will render as a co-author, but
        it belongs to no account, so it cannot appear in the contributors
        graph. Telling the user which of the two they have is the difference
        between the feature working and appearing to.
        """
        if _LINKABLE_NOREPLY.match(self.email):
            return True
        return not self.email.endswith("@users.noreply.github.com")

    def env(self) -> dict[str, str]:
        """Environment overrides that make git author a commit as this identity.

        Set through the environment rather than ``git config`` so nothing is
        written into the user's repository or global config — Citrine should
        not be quietly rewriting who the user commits as.
        """
        return {
            "GIT_AUTHOR_NAME": self.name,
            "GIT_AUTHOR_EMAIL": self.email,
            "GIT_COMMITTER_NAME": self.name,
            "GIT_COMMITTER_EMAIL": self.email,
        }


def citrine_identity() -> Identity:
    """The identity Citrine commits as, honouring environment overrides."""
    name = os.environ.get(NAME_ENV, "").strip() or DEFAULT_NAME

    email = os.environ.get(EMAIL_ENV, "").strip()
    if not email or not _EMAIL_PATTERN.match(email):
        email = DEFAULT_EMAIL

    # A name containing a newline or angle bracket would forge a second trailer
    # line, or break the `Name <email>` form git parses.
    name = name.replace("\n", " ").replace("\r", " ")
    name = name.replace("<", "").replace(">", "").strip() or DEFAULT_NAME

    return Identity(name=name[:100], email=email)


def add_coauthor_trailer(message: str, identity: Identity | None = None) -> str:
    """Append Citrine's ``Co-Authored-By:`` trailer to a commit message.

    Idempotent: re-running over a message that already credits this identity
    leaves it alone, so amending a commit does not stack duplicate trailers.

    Trailers must sit in their own paragraph at the end of the message or git —
    and GitHub — will not parse them.
    """
    who = identity or citrine_identity()
    body = message.rstrip()

    if who.trailer.lower() in body.lower():
        return body + "\n"

    separator = "\n" if _ends_with_trailer_block(body) else "\n\n"
    return f"{body}{separator}{who.trailer}\n"


def _ends_with_trailer_block(message: str) -> bool:
    """Whether the message already ends in a trailer paragraph.

    Deliberately paragraph-based rather than "does the last line look like
    `Key: value`". A conventional-commit subject — ``feat: add a thing`` — is
    indistinguishable from a trailer line on its own, so a line-level test
    appends the trailer directly under the subject with no blank line, and git
    then parses neither of them as trailers.
    """
    paragraphs = re.split(r"\n\s*\n", message.strip())
    if len(paragraphs) < 2:
        # Subject only: whatever it looks like, it is not a trailer block.
        return False

    last = paragraphs[-1].splitlines()
    return bool(last) and all(re.match(r"^[A-Za-z][A-Za-z-]*: ", line) for line in last)
