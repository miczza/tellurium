"""What the docs promise about "Done" stays within what the banner does: a page
can make "Done" invisible and lay it over its own button (a person's real click
then ends the wait), so "Done" alone does not prove a sign-in."""

from __future__ import annotations

import re
from pathlib import Path

import tellurium.browser.human as human

README = (Path(__file__).parents[2] / "README.md").read_text()


def _section(title: str) -> str:
    start = README.index(title)
    end = re.compile(r"\n#{2,4} ").search(README, start + len(title))
    return " ".join(README[start : end.start() if end else len(README)].split())


def test_the_module_does_not_claim_the_page_cannot_fake_done():
    assert "cannot pretend" not in human.__doc__


def test_the_readme_names_an_invisible_done_laid_over_the_page():
    limits = _section("#### Asking a person for help")
    assert "opacity" in limits
    assert "real click" in limits


def test_signing_in_by_hand_advises_a_validator():
    by_hand = _section("### Signing in by hand")
    assert "does not prove" in by_hand
    assert "@session.validate" in by_hand
