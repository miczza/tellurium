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


async def test_the_reports_own_commands_leave_a_tree_in_flight_shared(
    browser, local_server, monkeypatch
):
    """The report asks Chrome whether it answers on the test's own pipe. A
    snapshot that finds a tree request in flight shares it only if nothing that
    may change the page went out since: the report's ``Runtime.evaluate`` must
    not count as such, or the test it watches sees two ``getFullAXTree``
    (``test_snapshot_inflight``, fallen once in a loaded gate)."""
    from tellurium.browser.refs import RefMap
    from tellurium.browser.snapshot import take_snapshot

    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_shadow.html")
    sent: list[str] = []
    send = tab._session.send

    async def counting(method, params=None, timeout=None):
        if method == "Accessibility.getFullAXTree":
            sent.append(method)
        return await send(method, params, timeout)

    monkeypatch.setattr(tab._session, "send", counting)
    # The session's evaluate waits in the renderer behind the tree: ~3 s here,
    # past the probe's 5 s on a slow macOS runner (43709697878).
    monkeypatch.setattr(hang_probe, "LIVENESS_TIMEOUT", scaled(60))
    first = asyncio.ensure_future(
        take_snapshot(tab._session, RefMap(), selector="h1", snapshot_timeout=scaled(60))
    )
    while not sent:
        await asyncio.sleep(0)
    expr = {"expression": "document.readyState", "returnByValue": True}
    router = tab._session.router
    before = router._next_msg_id
    checks = asyncio.gather(
        hang_probe._check("root", router.root, "Browser.getVersion", {}),
        hang_probe._check("session", tab._session, "Runtime.evaluate", expr),
    )
    while router._next_msg_id < before + 2:  # both sent, as the report sends them
        await asyncio.sleep(0)
    second = await take_snapshot(
        tab._session, RefMap(), selector="body", snapshot_timeout=scaled(60)
    )
    checks = await checks
    assert (await first).startswith('- heading "Web component"')
    assert "Shadow 39999" in second
    assert all(" ok in " in line for line in checks), checks
    assert len(sent) == 1
