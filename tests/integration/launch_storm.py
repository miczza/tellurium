"""Many launches of Chrome in a row, to measure how often a fresh Chrome goes
mute (rosso noto 1 of R4: macOS, Chrome mute right after ``attachToTarget``).

Not part of the suite (no ``test_`` prefix): run it by path, on the CI with
``-f tests=tests/integration/launch_storm.py``. Each launch is a test of its
own, like the suite's ``browser`` fixture followed by a first tab, so the hang
probe reports a mute Chrome as it does in the suite. ``$TELLURIUM_STORM`` sets
the number of launches, ``$TELLURIUM_STORM_SECONDS`` the time they may take
in all (the job's own limit); the launches past it are skipped.
"""

from __future__ import annotations

import os
import time

import pytest

LAUNCHES = int(os.environ.get("TELLURIUM_STORM", "900"))
BUDGET = float(os.environ.get("TELLURIUM_STORM_SECONDS", "1500"))
_started = time.monotonic()


@pytest.mark.parametrize("launch", range(LAUNCHES))
async def test_a_fresh_chrome_answers_its_first_tab(launch, local_server):
    from tellurium import Browser

    if time.monotonic() - _started > BUDGET:
        pytest.skip("the storm's time is spent")
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.new_tab(f"{local_server}/tree.html")
        heading = await tab.select("#card-1 h3")
        assert await heading.text() == "Widget"
    finally:
        await browser.close()
