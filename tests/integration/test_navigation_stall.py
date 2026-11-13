"""A navigation through a stall of Chrome longer than the default deadline.

A Windows runner held a navigation's request 25 s (probably while taking a
volume shadow copy: seen in one stall), and a red went past 29.5 s: with nothing wrong in tellurium, the 30 s
of ``Tab.get`` without a timeout expired. The CI stretches that default
(``tests.timeout_scale``, factor 3: 90 s), read at each call. Here Chrome's
browser process is frozen (``SIGSTOP``, on Windows ``NtSuspendProcess``) for
:data:`STALL` seconds, between the two, from right before ``Page.navigate``:
the default deadline gives up inside the stall, the stretched one rides it
out and the page loads once Chrome is thawed.
"""

from __future__ import annotations

import asyncio

import pytest

from tellurium import NavigationTimeoutError
from tellurium.browser import navigation
from tests import hang_probe
from tests.process_freeze import freeze, thaw
from tests.timeout_scale import _stretched

#: The default users get (read before any test stretches it).
DEFAULT = navigation.NAVIGATION_TIMEOUT
#: What the CI's factor 3 makes of it.
STRETCHED = _stretched(DEFAULT, 3.0)
#: How long Chrome stays frozen: past the default, inside the stretched one.
STALL = 40.0


@pytest.mark.parametrize(
    ("deadline", "rides_it_out"),
    [(DEFAULT, False), (STRETCHED, True)],
    ids=["default", "stretched"],
)
async def test_a_navigation_rides_out_a_stall_of_chrome_only_with_the_stretched_default(
    browser, local_server, monkeypatch, deadline, rides_it_out
):
    assert DEFAULT < STALL < STRETCHED
    # A stall made on purpose: no report of the probe, which would read as a real one.
    monkeypatch.setattr(hang_probe, "watch_after", lambda *args, **kwargs: None)
    monkeypatch.setattr(navigation, "NAVIGATION_TIMEOUT", deadline)
    tab = browser.main_tab
    await tab.get(f"{local_server}/basic.html")  # Page enabled: the stall hits Page.navigate
    pid = browser._proc.process.pid
    loop = asyncio.get_running_loop()
    freeze(pid)
    try:
        started = loop.time()
        navigating = asyncio.ensure_future(tab.get(f"{local_server}/form.html"))
        await asyncio.wait({navigating}, timeout=STALL)
        stalled = loop.time() - started
    finally:
        thaw(pid)
    if rides_it_out:
        assert not navigating.done(), "the navigation ended inside the stall"
        await asyncio.wait_for(navigating, deadline)
        assert tab.url.endswith("/form.html")
        assert loop.time() - started >= STALL
    else:
        assert navigating.done(), f"still navigating after a {stalled:.1f} s stall"
        with pytest.raises(NavigationTimeoutError) as caught:
            navigating.result()
        assert caught.value.timeout == DEFAULT and caught.value.phase == "commit"
