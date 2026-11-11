"""A Chrome that stops answering leaves a diagnosis: the hang probe against a real Chrome.

Chrome's browser process is frozen (``SIGSTOP``, on Windows
``NtSuspendProcess``) while a command waits for it; the probe's report must
hold the test's chain of awaits and Chrome as each system shows it frozen.
On the CI the report lands in the job's artifact like any other.
"""

from __future__ import annotations

import sys

import pytest

from tests import hang_probe
from tests.process_freeze import frozen

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
    assert "=== end: Browser.getVersion TimeoutError after 6." in text
