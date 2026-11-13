"""Chrome's answer deadlines, stretched on slow CI runners.

The Windows and macOS runners stall for whole seconds with nothing wrong in
tellurium: on Windows a renderer (and once the whole machine, ``Get-Process``
included) went mute up to 27 s; macOS runners start at load 30-40 while
Spotlight indexes the fresh VM. A deadline sized for a Chrome that answers in
milliseconds expires there. ``TELLURIUM_TEST_TIMEOUT_SCALE``, set by the CI on
those jobs only, multiplies the waits for Chrome's answer during the
integration tests; the library's defaults stay what users get. The stalls
are absolute, not proportional to the wait: with a factor above 1 a scaled
wait is at least :data:`FLOOR` seconds, past the longest stall measured.

Scaled: :attr:`SessionRouter.default_timeout` (read at each send),
``robots.FETCH_TIMEOUT`` and ``robots._OPEN_TIMEOUT``, the ``CLOSE_GRACE`` of
``process`` and ``raw_chrome`` (how long Chrome gets to exit on its own after
``Browser.close``), the cookie calls of a session (``session_cookies.TIMEOUT``,
``session.LIVE_SAVE_TIMEOUT``) and the login's CDP calls
(``login_command.CALL_TIMEOUT``), the default deadline of a navigation and of
its ``Page.enable`` (``navigation.NAVIGATION_TIMEOUT``, ``LIFECYCLE_TIMEOUT``:
a Windows runner taking a shadow copy held a request 25 s, shown by
``test_navigation_stall.py``), all module globals read at call time; and
the tests' own answer bounds that go through :func:`scaled`. A ``tellurium``
command a test starts (the MCP server of ``test_mcp_http.py``) gets the
navigation's two from the test's process through ``tests.scaled_cli``; its
other deadlines are the command's own.
Not scaled: every deadline a test makes expire on purpose and asserts on
(``test_navigation_timeout.py``, explicit short ``timeout=`` in tests,
``_bounded``, the MCP's deadlines), and defaults of arguments, which are fixed
when the function is defined. Except where Chrome must answer before the
deadline expires for the expiry to mean something: the load-phase timeout of
``test_navigation_timeout.py`` needs the commit inside it, so it is scaled and
its page never finishes loading.
"""

from __future__ import annotations

import math
import os

import pytest

from tellurium.browser import navigation, raw_chrome, robots
from tellurium.browser import process as process_module
from tellurium.cdp.transport._session import SessionRouter
from tellurium.session import login_command, session, session_cookies

ENV = "TELLURIUM_TEST_TIMEOUT_SCALE"
#: Least scaled wait when the factor is above 1: the longest stall measured on
#: the runners is 27 s (Windows, R3-B), a 5 s wait x 3 is still short of it.
FLOOR = 30.0
#: Most a scaled wait grows to: a wait that expires must end the test before
#: pytest-timeout (300 s on the scaled jobs) ends the whole shard, which on
#: Windows leaves no report. A wait already longer stays as it is.
CEILING = 240.0

#: Owner and attribute of each deadline on an answer from Chrome that is scaled.
SCALED: tuple[tuple[object, str], ...] = (
    (SessionRouter, "default_timeout"),
    (robots, "FETCH_TIMEOUT"),
    (robots, "_OPEN_TIMEOUT"),
    (process_module, "CLOSE_GRACE"),
    (raw_chrome, "CLOSE_GRACE"),
    (session_cookies, "TIMEOUT"),
    (session, "LIVE_SAVE_TIMEOUT"),
    (login_command, "CALL_TIMEOUT"),
    (navigation, "NAVIGATION_TIMEOUT"),
    (navigation, "LIFECYCLE_TIMEOUT"),
)


def factor() -> float:
    """The factor from the environment, 1 when unset; ``ValueError`` when not a
    finite positive number (a typo must not silently mean 1)."""
    raw = os.environ.get(ENV, "").strip()
    if not raw:
        return 1.0
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and value > 0):
        raise ValueError(f"{ENV}={raw!r}: a finite positive number is expected")
    return value


def scaled(seconds: float) -> float:
    """*seconds* times the factor, at least :data:`FLOOR` and at most
    :data:`CEILING` when the factor is above 1: a test's own bound on an
    answer from Chrome."""
    return _stretched(seconds, factor())


def _stretched(seconds: float, times: float) -> float:
    if times > 1.0:
        return max(seconds, min(max(seconds * times, FLOOR), CEILING))
    return seconds * times


def stretch(mp: pytest.MonkeyPatch) -> None:
    """Stretch every deadline in :data:`SCALED` like :func:`scaled` through *mp*,
    which gives them back."""
    times = factor()
    if times == 1.0:
        return
    for owner, name in SCALED:
        mp.setattr(owner, name, _stretched(getattr(owner, name), times))


@pytest.fixture(autouse=True)
def chrome_answer_deadlines_scaled():
    """Its own MonkeyPatch: a test calling ``monkeypatch.undo()`` keeps the factor."""
    with pytest.MonkeyPatch.context() as mp:
        stretch(mp)
        yield
