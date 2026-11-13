"""The hang probe: where tellurium and Chrome were when a command got no reply."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import subprocess
import sys
import time

import pytest

from tellurium.cdp.transport._base import CDPTransport
from tellurium.cdp.transport._session import SessionRouter
from tests import hang_probe, timeout_scale
from tests.await_chain import awaiting, tasks_report
from tests.process_freeze import frozen
from tests.process_snapshot import snapshot, trimmed_sample


async def test_every_task_is_listed_with_the_awaits_it_is_suspended_in():
    gate = asyncio.Event()

    async def waiting_for_chrome():
        await gate.wait()

    async def a_command_of_the_test():
        await waiting_for_chrome()

    task = asyncio.create_task(a_command_of_the_test(), name="the-test-command")
    await asyncio.sleep(0)
    try:
        report = tasks_report()
    finally:
        gate.set()
        await task
    assert "the-test-command" in report
    block = report.split("the-test-command", 1)[1]
    assert block.index("a_command_of_the_test") < block.index("waiting_for_chrome")
    # The task that asks is not in its own report.
    assert report.startswith("1 task(s)")


async def test_the_chain_goes_into_an_async_generator_like_a_fixture():
    gate = asyncio.Event()

    async def launching_chrome():
        await gate.wait()

    async def a_browser_fixture():
        await launching_chrome()
        yield "browser"

    async def setup():
        return await a_browser_fixture().__anext__()

    task = asyncio.create_task(setup())
    await asyncio.sleep(0)
    try:
        lines = awaiting(task.get_coro())
    finally:
        gate.set()
        await task
    text = "\n".join(lines)
    assert text.index("a_browser_fixture") < text.index("launching_chrome")


async def test_the_chain_names_the_future_it_ends_on():
    future = asyncio.get_running_loop().create_future()

    async def on_a_future():
        await future

    coro = on_a_future()
    task = asyncio.ensure_future(coro)
    await asyncio.sleep(0)
    try:
        lines = awaiting(coro)
    finally:
        future.set_result(None)
        await task
    assert "on_a_future" in lines[0]
    assert "Future" in lines[-1]


@pytest.fixture
def sleeper():
    """A child process that only sleeps, killed at the end."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    yield child
    child.kill()
    child.wait(10)


#: How each system shows a process frozen by :func:`frozen`.
FROZEN_MARK = {"linux": "state=T", "darwin": "state=T", "win32": "Suspended"}


def test_the_snapshot_of_a_frozen_process_shows_it_frozen(sleeper):
    with frozen(sleeper.pid):
        text = snapshot(sleeper.pid)
    assert str(sleeper.pid) in text
    assert FROZEN_MARK[sys.platform] in text


def test_a_thawed_process_runs_again(sleeper):
    with frozen(sleeper.pid):
        pass
    text = snapshot(sleeper.pid)
    assert FROZEN_MARK[sys.platform] not in text


def test_the_snapshot_of_a_process_gone_says_so():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(30)
    assert "no process" in snapshot(child.pid)


class SilentChrome(CDPTransport):
    """A pipe whose Chrome takes every command and never answers."""

    def __init__(self):
        self.sent: list[dict] = []
        self._never = asyncio.Event()

    async def send(self, data: bytes) -> None:
        self.sent.append(json.loads(data.rstrip(b"\0")))

    async def recv(self) -> dict:
        await self._never.wait()
        raise EOFError

    async def close(self) -> None:
        pass


class LateChrome(SilentChrome):
    """A pipe whose Chrome answers every command after *delay* seconds."""

    def __init__(self, delay: float):
        super().__init__()
        self._replies: asyncio.Queue = asyncio.Queue()
        self._delay = delay

    async def send(self, data: bytes) -> None:
        await super().send(data)
        loop = asyncio.get_running_loop()
        msg_id = self.sent[-1]["id"]
        loop.call_later(self._delay, self._replies.put_nowait, {"id": msg_id, "result": {}})

    async def recv(self) -> dict:
        return await self._replies.get()


@pytest.fixture
def probe(monkeypatch, tmp_path):
    """The probe installed, watching after 0.2 s the commands given at least 0.5 s."""
    monkeypatch.delenv(timeout_scale.ENV, raising=False)
    monkeypatch.setenv(hang_probe.ENV, str(tmp_path))
    monkeypatch.setattr(hang_probe, "WATCH", 0.2)
    monkeypatch.setattr(hang_probe, "MIN_LIMIT", 0.5)
    monkeypatch.setattr(hang_probe, "LIVENESS_TIMEOUT", 0.2)
    with hang_probe.installed():
        hang_probe.begin_test("tests/unit/test_hang_probe.py::probe")
        yield tmp_path


async def test_a_command_without_a_reply_leaves_a_report_with_the_python_tasks(probe):
    router = SessionRouter(SilentChrome())

    async def a_command_chrome_never_answers():
        await router.root.send("Page.navigate", {"url": "about:blank"}, timeout=1.0)

    with pytest.raises(TimeoutError):
        await a_command_chrome_never_answers()
    [report] = probe.iterdir()
    text = report.read_text()
    assert "Page.navigate" in text
    assert "tests/unit/test_hang_probe.py::probe" in text
    assert "a_command_chrome_never_answers" in text.split("Python tasks", 1)[1]
    assert "root Browser.getVersion: TimeoutError" in text
    assert "no Chrome process" in text
    assert "Page.navigate TimeoutError after 1.0" in text


async def test_a_command_answered_in_time_leaves_no_report(probe):
    router = SessionRouter(LateChrome(0.01))
    reader = asyncio.create_task(router.run())
    try:
        assert await router.root.send("Browser.getVersion", timeout=1.0) == {}
    finally:
        reader.cancel()
    assert not list(probe.iterdir())


async def test_a_late_answer_is_reported_with_its_delay(probe):
    router = SessionRouter(LateChrome(0.5))
    reader = asyncio.create_task(router.run())
    try:
        await router.root.send("Browser.getVersion", timeout=2.0)
    finally:
        reader.cancel()
    [report] = probe.iterdir()
    assert "Browser.getVersion answered after 0." in report.read_text()


async def test_a_deadline_shorter_than_the_least_watched_is_not_reported(probe):
    router = SessionRouter(SilentChrome())
    with pytest.raises(TimeoutError):
        await router.root.send("Runtime.evaluate", timeout=0.4)
    assert not list(probe.iterdir())


async def test_only_the_first_stall_of_a_test_is_reported_in_full(probe):
    router = SessionRouter(SilentChrome())
    for method in ("Page.enable", "Page.reload"):
        with pytest.raises(TimeoutError):
            await router.root.send(method, timeout=0.6)
    [report] = probe.iterdir()
    text = report.read_text()
    assert text.count("Python tasks") == 1
    assert "Page.enable TimeoutError after" in text
    assert "Page.reload TimeoutError after" in text


def test_the_watch_comes_before_the_deadline_and_scales_like_it(monkeypatch):
    monkeypatch.delenv(timeout_scale.ENV, raising=False)
    assert hang_probe.watch_after(5.0) is None
    assert hang_probe.watch_after(30.0) == 10.0
    assert hang_probe.watch_after(10.0) == 8.0
    assert hang_probe.watch_after(math.inf) == 10.0
    monkeypatch.setenv(timeout_scale.ENV, "3")
    assert hang_probe.watch_after(90.0) == 30.0
    assert hang_probe.watch_after(10.0) == 8.0
    # No deadline of its own (Page.navigate in a navigation of 30 s): before 30 s.
    assert hang_probe.watch_after(math.inf) == 20.0


def test_a_macos_sample_keeps_every_thread_and_where_chrome_is_loaded():
    threads = [
        f"    1752 Thread_{n}\n    + 1752 thread_start  (in libsystem_pthread.dylib) + 8\n"
        for n in range(400)
    ]
    sample = (
        "Analysis of sampling Google Chrome (pid 4771) every 1 millisecond\n"
        "Call graph:\n"
        + "".join(threads)
        + "\nTotal number in stack (recursive counted multiple times):\n"
        "        1752       __psynch_rw_wrlock  (in libsystem_kernel.dylib)\n\n"
        "Binary Images:\n"
        "       0x100190000 -        0x100193fff  com.google.Chrome (142.0.7444.60) <AB12> /Applications/Google Chrome.app/Contents/MacOS/Google Chrome\n"
        "       0x11d398000 -        0x12a3fffff  com.google.Chrome.framework (142.0.7444.60) <CD34> /Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework/Versions/142.0.7444.60/Google Chrome Framework\n"
        "       0x186ed0000 -        0x186f6ffff  dyld (1.0) <EF56> /usr/lib/dyld\n"
    )
    text = trimmed_sample(sample)
    assert "Thread_399" in text
    assert "__psynch_rw_wrlock" in text
    assert "0x11d398000" in text and "Google Chrome Framework" in text
    assert "/usr/lib/dyld" not in text


async def test_a_navigation_cut_short_from_outside_is_reported(probe):
    """Like ``Tab.get``: ``Page.navigate`` has no deadline of its own, the
    navigation's ``wait_for`` cancels it."""
    router = SessionRouter(SilentChrome())

    async def a_navigation_of_the_test():
        await router.root.send("Page.navigate", {"url": "about:blank"}, timeout=math.inf)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(a_navigation_of_the_test(), 0.5)
    [report] = probe.iterdir()
    text = report.read_text()
    assert "Page.navigate (session root) pending" in text and "deadline infs" in text
    assert "a_navigation_of_the_test" in text.split("Python tasks", 1)[1]
    assert "root Browser.getVersion: TimeoutError" in text
    assert "no Chrome process" in text
    assert "=== end: Page.navigate CancelledError after 0.5" in text


class _AChrome:
    """What the probe reads of a ``BrowserProcess``: its pipe and its process."""

    def __init__(self, transport, process):
        self.transport, self.process = transport, process


def test_a_test_that_falls_right_after_the_warning_still_leaves_the_report(
    probe, monkeypatch, sleeper
):
    """The test does not wait for the report and its loop closes at once: what
    was known at the warning is on disk already, Chrome's snapshot follows."""
    monkeypatch.setattr(hang_probe, "LIVENESS_TIMEOUT", 5.0)  # the checks outlast the test
    monkeypatch.setattr(hang_probe, "REPORT_WAIT", 0.0)  # and nobody waits for them

    async def a_test_that_falls():
        router = SessionRouter(SilentChrome())
        chrome = _AChrome(router._transport, sleeper)
        hang_probe._procs.add(chrome)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                router.root.send("Page.navigate", {"url": "about:blank"}, timeout=math.inf), 0.5
            )
        [report] = probe.iterdir()
        text = report.read_text()
        assert "Page.navigate (session root) pending" in text
        assert "a_test_that_falls" in text.split("Python tasks", 1)[1]

    asyncio.run(a_test_that_falls())
    [report] = probe.iterdir()
    text = report.read_text()
    assert f"--- Chrome {sleeper.pid} (this pipe):" in text
    assert str(sleeper.pid) in text.split(f"--- Chrome {sleeper.pid} (this pipe):", 1)[1]
    assert "does Chrome answer? cut short: CancelledError" in text
    assert "=== end: Page.navigate CancelledError after 0.5" in text


async def test_a_full_report_starts_its_file_afresh(probe):
    stale = probe / "tests_unit_test_hang_probe.py_probe.txt"
    stale.write_text("=== end: Page.navigate answered after 1.0s\n")
    router = SessionRouter(SilentChrome())
    with pytest.raises(TimeoutError):
        await router.root.send("Page.enable", timeout=0.6)
    text = stale.read_text()
    assert "answered after 1.0s" not in text
    assert "Page.enable TimeoutError after" in text


def test_without_the_variable_the_reports_go_to_a_folder_of_this_run(monkeypatch):
    monkeypatch.delenv(hang_probe.ENV, raising=False)
    folder = hang_probe.report_dir()
    assert folder == hang_probe.report_dir()
    assert folder.parent.name == "tellurium-hang-reports"
    assert str(os.getpid()) in folder.name


def test_the_end_of_a_command_waits_for_a_snapshot_as_long_as_its_commands_may_take():
    """``sample`` of a frozen Chrome on macOS takes over 20 s (run 43390297210):
    the end waits for it unless the snapshot itself is stuck past its commands'
    own timeout."""
    from tests import process_snapshot

    assert hang_probe.REPORT_WAIT > process_snapshot.COMMAND_TIMEOUT + 10


async def test_an_answer_after_the_warning_comes_back_at_once(probe, monkeypatch, sleeper):
    """The probe never holds an answer: Chrome answers at 0.5 s, the report's
    snapshot takes 3 s, and a caller's wait_for of 1.5 s still has the answer."""
    monkeypatch.setattr(
        hang_probe, "snapshot", lambda pid, since=None: time.sleep(3) or "a slow snapshot"
    )
    router = SessionRouter(LateChrome(0.5))
    chrome = _AChrome(router._transport, sleeper)
    hang_probe._procs.add(chrome)
    reader = asyncio.create_task(router.run())
    try:
        navigate = router.root.send("Page.navigate", {"url": "about:blank"}, timeout=math.inf)
        assert await asyncio.wait_for(navigate, 1.5) == {}
    finally:
        reader.cancel()
    [report] = probe.iterdir()
    assert "=== end: Page.navigate answered after 0.5" in report.read_text()


async def test_the_report_lists_the_requests_to_the_test_servers_around_the_send(probe):
    """Whether the server got the navigation's request, and when it answered:
    a stall before the request is not one after the response (R4-B)."""
    router = SessionRouter(LateChrome(0.6))
    reader = asyncio.create_task(router.run())
    early = hang_probe.request_arrived("127.0.0.1:1/early.html")
    hang_probe.request_answered(early)
    await asyncio.sleep(0.05)  # past a tick of Windows' monotonic clock (15.6 ms)
    loop = asyncio.get_running_loop()

    def serve(path: str, answer: bool) -> None:
        entry = hang_probe.request_arrived(path)
        if answer:
            hang_probe.request_answered(entry)

    loop.call_later(0.1, serve, "127.0.0.1:1/frame.html", True)
    loop.call_later(0.4, serve, "127.0.0.1:1/late.html", False)
    try:
        await router.root.send("Page.navigate", {"url": "about:blank"}, timeout=2.0)
    finally:
        reader.cancel()
    [report] = probe.iterdir()
    text = report.read_text()
    head, end = text.split("=== end", 1)
    assert "early.html" not in text
    assert re.search(r"\+0\.1\ds GET 127.0.0.1:1/frame.html, answered at \+0\.1\ds", head)
    assert "late.html" not in head
    assert re.search(r"\+0\.4\ds GET 127.0.0.1:1/late.html, not answered", end)


async def test_the_report_says_when_the_send_was_on_the_clock_of_the_snapshot(probe):
    router = SessionRouter(SilentChrome())
    before = time.time()
    with pytest.raises(TimeoutError):
        await router.root.send("Page.enable", timeout=0.6)
    [report] = probe.iterdir()
    [sent] = re.findall(r"sent at Unix time ([\d.]+)", report.read_text())
    assert before - 0.1 < float(sent) < before + 0.1


async def test_a_navigation_shorter_than_the_watch_is_watched_within_its_own_deadline(
    probe, monkeypatch
):
    """``Page.navigate`` has no deadline of its own: the navigation's bounds it,
    and a ``tab.get(timeout=1)`` is watched within it, not at the fixed watch."""
    from tellurium.browser import tab as tab_module
    from tellurium.browser.navigation import NavigationTimeoutError

    monkeypatch.setattr(hang_probe, "WATCH", 10.0)
    monkeypatch.setattr(hang_probe, "UNBOUNDED_WATCH", 10.0)
    router = SessionRouter(SilentChrome())
    with pytest.raises(NavigationTimeoutError):
        await tab_module.navigate(router.root, "about:blank", wait_until="load", timeout=1.0)
    [report] = probe.iterdir()
    assert re.search(r"Page.navigate \(session root\) pending for 0\.[78]s", report.read_text())


async def test_the_end_says_how_long_the_command_took_not_the_report(probe, monkeypatch, sleeper):
    """A slow snapshot (seconds on Windows and macOS) does not stretch the
    duration of the command in the end line."""
    monkeypatch.setattr(
        hang_probe, "snapshot", lambda pid, since=None: time.sleep(1.5) or "a slow snapshot"
    )
    router = SessionRouter(SilentChrome())
    hang_probe._procs.add(_AChrome(router._transport, sleeper))
    with pytest.raises(TimeoutError):
        await router.root.send("Page.enable", timeout=0.6)
    [report] = probe.iterdir()
    assert "=== end: Page.enable TimeoutError after 0.6s" in report.read_text()
