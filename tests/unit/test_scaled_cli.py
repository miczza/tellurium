"""The ``tellurium`` command a test starts gets the navigation deadlines of the
test's process, and only those."""

import json
import sys

from tellurium.browser import navigation, process, raw_chrome
from tellurium.session import session_cookies
from tests import scaled_cli, timeout_scale


def test_the_child_gets_the_stretched_navigation_deadlines_and_nothing_else(monkeypatch):
    """On a slow runner (factor 3) the child navigates with 90 s and 10 -> 30 s,
    but Chrome's close grace and the cookie calls stay the command's own: a
    test bounding how long the server takes to stop (``test_sigterm...``)
    measures the command users get."""
    monkeypatch.setenv(timeout_scale.ENV, "3")
    timeout_scale.stretch(monkeypatch)
    argv = scaled_cli.command("mcp", "--http")
    assert argv[-2:] == ["mcp", "--http"]
    carried = {(module, name): value for module, _, name, value in json.loads(argv[2])}
    assert carried == {
        ("tellurium.browser.navigation", "NAVIGATION_TIMEOUT"): 90.0,
        ("tellurium.browser.navigation", "LIFECYCLE_TIMEOUT"): 30.0,
    }


def test_the_child_sets_what_it_gets_before_the_command_runs(monkeypatch):
    seen = {}

    def the_command():
        seen.update(
            navigation=navigation.NAVIGATION_TIMEOUT,
            grace=(process.CLOSE_GRACE, raw_chrome.CLOSE_GRACE),
            cookies=session_cookies.TIMEOUT,
        )
        return 0

    defaults = (process.CLOSE_GRACE, raw_chrome.CLOSE_GRACE), session_cookies.TIMEOUT
    monkeypatch.setattr("tellurium.cli.main", the_command)
    monkeypatch.setattr(sys, "argv", list(sys.argv))  # the child sets its own
    monkeypatch.setattr(navigation, "NAVIGATION_TIMEOUT", navigation.NAVIGATION_TIMEOUT)
    deadlines = json.dumps([["tellurium.browser.navigation", "", "NAVIGATION_TIMEOUT", 7.5]])
    assert scaled_cli.main([deadlines, "mcp"]) == 0
    assert seen == {"navigation": 7.5, "grace": defaults[0], "cookies": defaults[1]}
