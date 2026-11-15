"""SessionPool with real Chrome: never more browsers than the cap (counted
from /proc, not from the pool), one seed and one cookie jar per identity, a
session open elsewhere is neither opened nor deleted, and an open cancelled
mid-launch leaves no Chrome and no slot taken."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from tellurium.session import Session, SessionBusyError, SessionPool
from tests.integration.session_child import kill_holder, start_holder
from tests.platform_marks import needs_proc
from tests.private_temp import FAILING_EXECUTABLE
from tests.timeout_scale import scaled


def _running(directory: str) -> set[str]:
    """The sessions of *directory* some live process (Chrome or a child of it)
    has as its ``--user-data-dir``."""
    marker = os.fsencode(os.path.join(directory, ""))
    found = set()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read()
        except OSError:
            continue
        at = cmdline.find(b"--user-data-dir=" + marker)
        if at < 0:
            continue
        rest = cmdline[at + len(b"--user-data-dir=") + len(marker) :]
        found.add(os.fsdecode(rest.split(b"/")[0]))
    return found


class Census:
    """Samples the Chrome instances of a pool directory until stopped."""

    def __init__(self, directory: str):
        self.directory = directory
        self.peak = 0
        self.seen: set[str] = set()
        self._task: asyncio.Task | None = None

    async def __aenter__(self):
        self._task = asyncio.create_task(self._sample())
        return self

    async def __aexit__(self, *exc):
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def _sample(self):
        while True:
            now = await asyncio.to_thread(_running, self.directory)
            self.peak = max(self.peak, len(now))
            self.seen |= now
            await asyncio.sleep(0.02)


@needs_proc
async def test_six_identities_two_browsers_at_a_time(tmp_path, local_server):
    pool = SessionPool(tmp_path, max_browsers=2, headless=True)
    names = [f"id{i}" for i in range(6)]
    before: dict[str, str] = {}

    async def visit(name: str):
        async with pool.open(name) as browser:
            tab = await browser.get(f"{local_server}/basic.html")
            before[name] = await tab.eval("document.cookie")
            await tab.eval(f"document.cookie = 'who={name}; path=/'")
            await asyncio.sleep(0.3)  # overlap with the others

    async with Census(str(tmp_path)) as census:
        await asyncio.wait_for(asyncio.gather(*(visit(n) for n in names)), 240)
    assert census.peak == 2
    assert census.seen == set(names)
    assert await asyncio.to_thread(_running, str(tmp_path)) == set()

    assert before == {n: "" for n in names}  # no jar saw another identity's cookie
    seeds = set()
    for name in names:
        folder = Path(pool.path(name))
        seeds.add(json.loads((folder / "session.json").read_text())["seed"])
        jar = json.loads((folder / "cookies.json").read_text())["cookies"]
        assert [(c["name"], c["value"]) for c in jar] == [("who", name)]
    assert len(seeds) == 6
    assert await pool.list() == names


async def test_a_session_open_in_another_process(tmp_path):
    """E2 on every system: another process holds the session, so open and
    delete get SessionBusyError and the folder stays where it is."""
    pool = SessionPool(tmp_path, max_browsers=1, headless=True)
    path = pool.path("shared")
    holder = await start_holder(path)
    try:
        with pytest.raises(SessionBusyError) as info:
            async with pool.open("shared"):
                pass
        assert info.value.pid == holder.pid
        with pytest.raises(SessionBusyError) as info:
            await pool.delete("shared")
        assert info.value.pid == holder.pid
        assert os.path.isdir(os.path.join(path, "chrome"))
        assert not [n for n in os.listdir(tmp_path) if ".deleted-" in n]  # nothing renamed
        async with pool.open("other") as browser:  # the refusals took no slot
            assert await browser.main_tab.eval("1 + 1") == 2
    finally:
        kill_holder(holder)
        await holder.wait()
    await pool.delete("shared")  # its holder gone, the folder goes too
    assert await pool.list() == ["other"]


@needs_proc
async def test_cancelled_mid_launch_leaves_no_chrome(tmp_path):
    pool = SessionPool(tmp_path, max_browsers=1, headless=True)
    entered = asyncio.Event()

    async def use():
        async with pool.open("a"):
            entered.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(use())
    for _ in range(600):  # Chrome is up, the open has not returned yet
        if await asyncio.to_thread(_running, str(tmp_path)) or entered.is_set():
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread(_running, str(tmp_path)) == set()
    async with pool.open("b") as browser:  # the slot came back
        assert await asyncio.wait_for(browser.main_tab.eval("1 + 1"), 30) == 2


@needs_proc
async def test_a_failed_validation_closes_chrome_and_frees_the_slot(tmp_path):
    from tellurium.session import SessionInvalidError

    pool = SessionPool(tmp_path, max_browsers=1, headless=True)
    session = await pool.create("a")

    @session.validate
    async def signed_in(tab):
        return False

    with pytest.raises(SessionInvalidError):
        async with pool.open(session):
            pass
    assert await asyncio.to_thread(_running, str(tmp_path)) == set()
    async with pool.open("b") as browser:  # the only slot came back
        assert await asyncio.wait_for(browser.main_tab.eval("1 + 1"), 30) == 2


@needs_proc
async def test_a_failed_launch_frees_the_slot(tmp_path):
    pool = SessionPool(tmp_path, max_browsers=1, headless=True)
    from tellurium.browser.launcher import LaunchError

    with pytest.raises(LaunchError):  # a "Chrome" that exits at once
        async with pool.open("a", executable=FAILING_EXECUTABLE):
            pass
    async with pool.open("b") as browser:
        assert await asyncio.wait_for(browser.main_tab.eval("1 + 1"), 30) == 2
    assert await asyncio.to_thread(_running, str(tmp_path)) == set()


@needs_proc
def test_one_pool_in_two_asyncio_runs(tmp_path):
    """The slots belong to the loop of the open: a second asyncio.run with the
    same pool opens (and queues on its one slot) as the first did."""
    pool = SessionPool(tmp_path, max_browsers=1, headless=True)

    async def two_at_once():
        async def use(name):
            async with pool.open(name) as browser:
                return await asyncio.wait_for(browser.main_tab.eval("1 + 1"), 30)

        return await asyncio.wait_for(asyncio.gather(use("a"), use("b")), 120)

    assert asyncio.run(two_at_once()) == [2, 2]
    assert asyncio.run(two_at_once()) == [2, 2]
    assert _running(str(tmp_path)) == set()


#: Longest wait from one browser closed to the next one's launch: a lost turn
#: of polling would be a poll interval; the handoff itself is a loop turn.
HANDOFF = 1.0


async def test_three_opens_in_a_loop_wait_no_more_than_a_launch(tmp_path, monkeypatch):
    """E5: one slot, three identities opened over and over. Turns go round
    in order, and between one browser leaving and the next entering there
    is a close and a launch, never a lost turn of polling.

    Each close and launch is timed in the same run, around ``Session.start``:
    on Windows a runner stall (a shadow copy, R4) stretched one of them to
    20 s against 1.8 s for the warm launch, so a bound on the whole gap
    measured off another launch did not hold (rosso noto 4, R4-D). What the
    pool owns is the handoff: from one start's exit to the next one's entry."""
    loop = asyncio.get_running_loop()
    spans: list[tuple[str, float, float]] = []  # name, start entered, start exited
    real_start = Session.start

    @asynccontextmanager
    async def timed_start(self, **kwargs):
        entered = loop.time()
        try:
            async with real_start(self, **kwargs) as browser:
                yield browser
        finally:
            spans.append((self.name, entered, loop.time()))

    monkeypatch.setattr(Session, "start", timed_start)
    pool = SessionPool(tmp_path, max_browsers=1, headless=True)
    async with pool.open("warm") as browser:  # the first launch of the run, alone
        await browser.main_tab.eval("1")
    turns: list[str] = []

    async def opener(name: str):
        for _ in range(2):
            async with pool.open(name) as browser:
                await browser.main_tab.eval("1")
                await asyncio.sleep(0.05)
                turns.append(name)

    await asyncio.wait_for(asyncio.gather(*(opener(n) for n in ("a", "b", "c"))), scaled(240))
    assert sorted(turns[:3]) == ["a", "b", "c"] and turns[3:] == turns[:3]  # round robin
    assert [name for name, *_ in spans[1:]] == turns
    handoffs = [nxt[1] - prev[2] for prev, nxt in zip(spans, spans[1:], strict=False)]
    assert all(h >= 0 for h in handoffs), ("two browsers at once", spans)
    assert max(handoffs) < HANDOFF, (handoffs, spans)
