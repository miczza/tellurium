"""SessionPool with real Chrome: never more browsers than the cap (counted
from /proc, not from the pool), one seed and one cookie jar per identity, a
session open elsewhere is neither opened nor deleted, and an open cancelled
mid-launch leaves no Chrome and no slot taken."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import pytest

from tellurium.session import SessionBusyError, SessionPool
from tests.integration.session_child import child_env
from tests.platform_marks import needs_posix_signals, needs_proc

_CHILD = str(Path(__file__).with_name("session_child.py"))


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


@needs_posix_signals
async def test_a_session_open_in_another_process(tmp_path):
    pool = SessionPool(tmp_path, max_browsers=1, headless=True)
    path = pool.path("shared")
    holder = await asyncio.create_subprocess_exec(
        sys.executable,
        _CHILD,
        "hold",
        path,
        env=child_env(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        assert (await asyncio.wait_for(holder.stdout.readline(), 60)).strip() == b"ready"
        with pytest.raises(SessionBusyError) as info:
            async with pool.open("shared"):
                pass
        assert info.value.pid == holder.pid
        with pytest.raises(SessionBusyError) as info:
            await pool.delete("shared")
        assert info.value.pid == holder.pid
        assert os.path.isdir(os.path.join(path, "chrome"))
        async with pool.open("other") as browser:  # the refusals took no slot
            assert await browser.main_tab.eval("1 + 1") == 2
    finally:
        try:
            os.killpg(holder.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
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
        async with pool.open("a", executable="/bin/false"):
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


async def test_three_opens_in_a_loop_wait_no_more_than_a_launch(tmp_path):
    """E5: one slot, three identities opened over and over. Turns go round
    in order, and between one browser leaving and the next entering there
    is a close and a launch, never a lost turn of polling."""
    pool = SessionPool(tmp_path, max_browsers=1, headless=True)
    loop = asyncio.get_running_loop()
    start = loop.time()
    async with pool.open("warm") as browser:  # reference: one launch, alone
        await browser.main_tab.eval("1")
    reference = loop.time() - start
    turns: list[tuple[str, float, float]] = []

    async def opener(name: str):
        for _ in range(2):
            async with pool.open(name) as browser:
                entered = loop.time()
                await browser.main_tab.eval("1")
                await asyncio.sleep(0.05)
                turns.append((name, entered, loop.time()))

    await asyncio.wait_for(asyncio.gather(*(opener(n) for n in ("a", "b", "c"))), 240)
    order = [t[0] for t in turns]
    assert sorted(order[:3]) == ["a", "b", "c"] and order[3:] == order[:3]  # round robin
    gaps = [nxt[1] - prev[2] for prev, nxt in zip(turns, turns[1:], strict=False)]
    assert max(gaps) < 2 * reference + 1.0, (gaps, reference)
