"""The ``tellurium`` command a test starts gets the navigation and robots.txt
deadlines of the test's process, and only those; a script of the tests gets
every scaled deadline."""

import json
import sys

from tellurium.browser import navigation, process, raw_chrome
from tellurium.session import session_cookies
from tests import scaled_cli, timeout_scale


def test_the_child_gets_the_stretched_navigation_deadlines_and_nothing_else(monkeypatch):
    """On a slow runner (factor 3) the child navigates with 90 s and 10 -> 30 s
    (and downloads robots.txt with 30 s),
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
        ("tellurium.browser.robots", "FETCH_TIMEOUT"): 30.0,
        ("tellurium.browser.robots", "_OPEN_TIMEOUT"): 30.0,
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


def test_the_mcp_server_gets_the_robots_deadlines_too(monkeypatch):
    """``--respect-robots``: the server downloads robots.txt before each
    navigation; a stalled runner past its 10 s makes it "nothing allowed"
    (``test_mcp_respect_robots...``, Windows)."""
    from tellurium.browser import robots

    monkeypatch.setenv(timeout_scale.ENV, "3")
    timeout_scale.stretch(monkeypatch)
    carried = {name: value for _, _, name, value in json.loads(scaled_cli.command("mcp")[2])}
    assert carried["FETCH_TIMEOUT"] == robots.FETCH_TIMEOUT == 30.0
    assert carried["_OPEN_TIMEOUT"] == robots._OPEN_TIMEOUT == 30.0


def test_a_script_of_the_tests_gets_every_scaled_deadline(monkeypatch, tmp_path):
    """A child the tests run for themselves (``session_child.py``) is part of
    the test: it waits for Chrome as long as the test's process does."""
    monkeypatch.setenv(timeout_scale.ENV, "3")
    timeout_scale.stretch(monkeypatch)
    script = tmp_path / "child.py"
    argv = scaled_cli.script(str(script), "write", "x")
    assert argv[-4:] == ["--script", str(script), "write", "x"]
    carried = {(owner, name) for _, owner, name, _ in json.loads(argv[2])}
    assert carried == {
        (o.__qualname__ if isinstance(o, type) else "", n) for o, n in timeout_scale.SCALED
    }


def test_a_script_runs_as_main_with_its_own_argv(monkeypatch, tmp_path):
    script = tmp_path / "child.py"
    out = tmp_path / "out.json"
    script.write_text(
        "import json, sys\n"
        "from tellurium.browser import navigation\n"
        "if __name__ == '__main__':\n"
        f"    open({str(out)!r}, 'w').write(json.dumps([sys.argv, navigation.NAVIGATION_TIMEOUT]))\n"
    )
    monkeypatch.setattr(sys, "argv", list(sys.argv))
    monkeypatch.setattr(navigation, "NAVIGATION_TIMEOUT", navigation.NAVIGATION_TIMEOUT)
    deadlines = json.dumps([["tellurium.browser.navigation", "", "NAVIGATION_TIMEOUT", 7.5]])
    scaled_cli.main([deadlines, "--script", str(script), "read", "p"])
    assert json.loads(out.read_text()) == [[str(script), "read", "p"], 7.5]


def test_what_the_command_gets_is_scaled_in_the_tests_process():
    """A deadline carried but not in ``timeout_scale.SCALED`` would reach the
    command as the library's default, never stretched."""
    assert set(scaled_cli.CARRIED) <= set(timeout_scale.SCALED)
