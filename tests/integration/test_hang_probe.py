"""A Chrome that stops answering leaves a diagnosis: the hang probe against a real Chrome.

Chrome's browser process is frozen (``SIGSTOP``, on Windows
``NtSuspendProcess``) while a command waits for it; the probe's report must
hold the test's chain of awaits and Chrome as each system shows it frozen.
On the CI the report lands in the job's artifact like any other.
"""

from __future__ import annotations

import asyncio
import math
import re
import sys

import pytest

from tests import hang_probe
from tests.process_freeze import frozen
from tests.timeout_scale import scaled

#: How each system's snapshot shows the frozen browser process.
FROZEN_MARK = {"linux": "state=T", "darwin": "state=T", "win32": "Suspended"}


async def _a_command_to_a_frozen_chrome(browser) -> None:
    await browser._router.root.send("Browser.getVersion", timeout=6.0)


async def test_a_frozen_chrome_leaves_python_tasks_and_its_own_state(browser, monkeypatch):
    monkeypatch.setattr(hang_probe, "MIN_LIMIT", 2.0)
    monkeypatch.setattr(hang_probe, "WATCH", 1.0)
    pid = browser._proc.process.pid
    before = len(hang_probe.reports)
    with frozen(pid):
        with pytest.raises(TimeoutError):
            await _a_command_to_a_frozen_chrome(browser)
    assert await browser._router.root.send("Browser.getVersion")  # thawed: it answers again
    [path] = hang_probe.reports[before:]
    text = path.read_text(encoding="utf-8")
    assert "test_a_frozen_chrome_leaves_python_tasks" in text.splitlines()[0]
    tasks = text.split("--- Python tasks", 1)[1]
    assert "_a_command_to_a_frozen_chrome" in tasks
    assert "root Browser.getVersion: TimeoutError" in text
    chrome = text.split(f"--- Chrome {pid} (this pipe):", 1)[1]
    assert FROZEN_MARK[sys.platform] in chrome
    if sys.platform == "darwin":
        assert "Call graph" in chrome or "Thread_" in chrome, chrome[:2000]
    # Chrome's browser process was born before the stalled send.
    assert re.search(rf"pid {pid} .*born=-\d+\.\d\ds", chrome), chrome[:2000]
    machine = text.split("--- the machine:", 1)[1]
    assert ("on the disk" if sys.platform == "win32" else "load average") in machine
    assert "=== end: Browser.getVersion TimeoutError after 6." in text


async def _a_navigation_of_the_test(tab) -> None:
    await tab._session.send("Page.navigate", {"url": "about:blank"}, timeout=math.inf)


async def test_a_navigation_cut_short_on_a_frozen_chrome_still_leaves_the_report(
    browser, monkeypatch
):
    """The path of the reds on Windows: ``Page.navigate`` has no deadline of its
    own, the navigation's ``wait_for`` cancels it and the test fails at once,
    without waiting for the report. It is on disk already, Chrome's snapshot
    follows while Chrome is still frozen."""
    monkeypatch.setattr(hang_probe, "WATCH", 1.0)
    monkeypatch.setattr(hang_probe, "UNBOUNDED_WATCH", 1.0)
    monkeypatch.setattr(hang_probe, "REPORT_WAIT", 0.0)
    pid = browser._proc.process.pid
    marker = f"--- Chrome {pid} (this pipe):"
    loop = asyncio.get_running_loop()
    before = len(hang_probe.reports)
    with frozen(pid):
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(_a_navigation_of_the_test(browser.main_tab), 2.5)
        [path] = hang_probe.reports[before:]
        text = path.read_text(encoding="utf-8")
        assert "test_a_navigation_cut_short_on_a_frozen_chrome" in text.splitlines()[0]
        assert "Page.navigate" in text and "deadline infs" in text
        assert "_a_navigation_of_the_test" in text.split("--- Python tasks", 1)[1]
        assert "=== end: Page.navigate CancelledError after 2." in text
        deadline = loop.time() + scaled(30)
        while marker not in text and loop.time() < deadline:
            await asyncio.sleep(0.2)
            text = path.read_text(encoding="utf-8")
    assert FROZEN_MARK[sys.platform] in text.split(marker, 1)[1], text[-2000:]
