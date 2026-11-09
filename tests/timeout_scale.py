"""Chrome's answer deadlines, stretched on slow CI runners.

The Windows and macOS runners stall for whole seconds with nothing wrong in
tellurium: on Windows a renderer (and once the whole machine, ``Get-Process``
included) went mute up to 27 s; macOS runners start at load 30-40 while
Spotlight indexes the fresh VM. A deadline sized for a Chrome that answers in
milliseconds expires there. ``TELLURIUM_TEST_TIMEOUT_SCALE``, set by the CI on
those jobs only, multiplies the waits for Chrome's answer during the
integration tests; the library's defaults stay what users get.

Scaled: :attr:`SessionRouter.default_timeout` (read at each send),
``robots.FETCH_TIMEOUT`` and ``robots._OPEN_TIMEOUT`` (module globals read at
call time), and the tests' own answer bounds that go through :func:`scaled`.
Not scaled: every deadline a test makes expire on purpose and asserts on
(``test_navigation_timeout.py``, explicit short ``timeout=`` in tests,
``_bounded``, the MCP's deadlines), and defaults of arguments, which are fixed
when the function is defined.
"""

from __future__ import annotations

import math
import os

import pytest

from tellurium.browser import robots
from tellurium.cdp.transport._session import SessionRouter

ENV = "TELLURIUM_TEST_TIMEOUT_SCALE"

#: Owner and attribute of each deadline on an answer from Chrome that is scaled.
SCALED: tuple[tuple[object, str], ...] = (
    (SessionRouter, "default_timeout"),
    (robots, "FETCH_TIMEOUT"),
    (robots, "_OPEN_TIMEOUT"),
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
    """*seconds* times the factor: a test's own bound on an answer from Chrome."""
    return seconds * factor()


def stretch(mp: pytest.MonkeyPatch) -> None:
    """Multiply every deadline in :data:`SCALED` through *mp*, which gives them back."""
    times = factor()
    if times == 1.0:
        return
    for owner, name in SCALED:
        mp.setattr(owner, name, getattr(owner, name) * times)


@pytest.fixture(autouse=True)
def chrome_answer_deadlines_scaled():
    """Its own MonkeyPatch: a test calling ``monkeypatch.undo()`` keeps the factor."""
    with pytest.MonkeyPatch.context() as mp:
        stretch(mp)
        yield
