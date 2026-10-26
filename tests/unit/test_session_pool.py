"""SessionPool without Chrome: Session.start is replaced by a fake that counts
the browsers "running", so the cap, the name claims and the clean-up on error
and cancellation can be driven step by step."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager

import pytest

from tellurium.session import Session, SessionBusyError, SessionPool
from tellurium.session.lock import SessionLock


class FakeChrome:
    """Stands in for Session.start: a browser runs from enter to exit."""

    def __init__(self):
        self.running: set[str] = set()
        self.peak = 0
        self.started: list[str] = []
        self.kwargs: list[dict] = []
        self.fail: set[str] = set()  # names whose launch raises
        self.gate: asyncio.Event | None = None  # when set, launches wait on it

    def install(self, monkeypatch):
        fake = self

        @asynccontextmanager
        async def start(session, **kwargs):
            fake.started.append(session.name)
            fake.kwargs.append(kwargs)
            fake.running.add(session.name)
            fake.peak = max(fake.peak, len(fake.running))
            try:
                if fake.gate is not None:
                    await fake.gate.wait()
                if session.name in fake.fail:
                    raise RuntimeError(f"launch of {session.name} failed")
                yield f"browser-{session.name}"
            finally:
                fake.running.discard(session.name)

        monkeypatch.setattr(Session, "start", start)
        return self


@pytest.fixture
def chrome(monkeypatch):
    return FakeChrome().install(monkeypatch)


async def _use(pool, name, hold=0.02):
    async with pool.open(name) as browser:
        assert browser == f"browser-{name}"
        await asyncio.sleep(hold)


async def test_never_more_browsers_than_the_cap(tmp_path, chrome):
    pool = SessionPool(tmp_path, max_browsers=2)
    await asyncio.wait_for(asyncio.gather(*(_use(pool, f"s{i}") for i in range(6))), 10)
    assert chrome.peak == 2
    assert sorted(chrome.started) == [f"s{i}" for i in range(6)]
    assert chrome.running == set()


async def test_a_failed_launch_gives_its_slot_back(tmp_path, chrome):
    pool = SessionPool(tmp_path, max_browsers=1)
    chrome.fail = {"bad0", "bad1", "bad2"}
    for name in sorted(chrome.fail):
        with pytest.raises(RuntimeError, match="failed"):
            await asyncio.wait_for(_use(pool, name), 2)
    await asyncio.wait_for(_use(pool, "good"), 2)


async def test_an_error_in_the_body_gives_the_slot_back(tmp_path, chrome):
    pool = SessionPool(tmp_path, max_browsers=1)
    with pytest.raises(LookupError):
        async with pool.open("a"):
            raise LookupError("body failed")
    await asyncio.wait_for(_use(pool, "b"), 2)
    assert chrome.running == set()


async def test_an_open_waiting_for_a_slot_can_be_cancelled(tmp_path, chrome):
    pool = SessionPool(tmp_path, max_browsers=1)
    release = asyncio.Event()

    async def holder():
        async with pool.open("a"):
            await release.wait()

    first = asyncio.create_task(holder())
    while "a" not in chrome.running:
        await asyncio.sleep(0.005)
    waiting = asyncio.create_task(_use(pool, "b"))
    await asyncio.sleep(0.05)
    assert chrome.started == ["a"]  # b waits for the slot
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    release.set()
    await asyncio.wait_for(first, 2)
    # The cancelled open took no slot and holds no name: both come back.
    await asyncio.wait_for(asyncio.gather(_use(pool, "b"), _use(pool, "c")), 2)
    assert chrome.peak == 1
    assert chrome.started[0] == "a" and sorted(chrome.started[1:]) == ["b", "c"]


async def test_cancelled_during_launch_gives_the_slot_back(tmp_path, chrome):
    pool = SessionPool(tmp_path, max_browsers=1)
    chrome.gate = asyncio.Event()  # the launch hangs
    task = asyncio.create_task(_use(pool, "a"))
    while "a" not in chrome.running:
        await asyncio.sleep(0.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert chrome.running == set()
    chrome.gate = None
    await asyncio.wait_for(_use(pool, "a"), 2)


async def test_same_name_twice_in_the_pool_is_busy_at_once(tmp_path, chrome):
    pool = SessionPool(tmp_path, max_browsers=1)
    async with pool.open("a"):
        with pytest.raises(SessionBusyError) as info:
            # Fails at once, not after waiting for the (taken) slot.
            await asyncio.wait_for(_use(pool, "a"), 1)
        assert info.value.pid == os.getpid()
        assert info.value.path == pool.path("a")


async def test_busy_in_another_holder_fails_before_taking_a_slot(tmp_path, chrome):
    pool = SessionPool(tmp_path, max_browsers=1)
    other = SessionLock(pool.path("a"))
    other.acquire()  # another lock: as another process would hold it
    try:
        async with pool.open("b"):  # the only slot is taken...
            with pytest.raises(SessionBusyError):
                await asyncio.wait_for(_use(pool, "a"), 2)  # ...and a still fails fast
    finally:
        other.release()
    assert "a" not in chrome.started


async def test_open_creates_a_missing_session_with_a_lasting_seed(tmp_path, chrome):
    pool = SessionPool(tmp_path)
    await _use(pool, "new")
    with open(os.path.join(pool.path("new"), "session.json")) as f:
        seed = json.load(f)["seed"]
    assert (await pool.get("new")).seed == seed
    assert await pool.list() == ["new"]


async def test_launch_defaults_and_overrides(tmp_path, chrome):
    pool = SessionPool(tmp_path, headless=True, proxy="http://a:1")
    async with pool.open("a", proxy="http://b:2"):
        pass
    assert chrome.kwargs == [{"headless": True, "proxy": "http://b:2"}]


async def test_open_takes_a_session_of_the_pool(tmp_path, chrome):
    pool = SessionPool(tmp_path)
    session = await pool.create("mario", seed=42)
    async with pool.open(session) as browser:
        assert browser == "browser-mario"
    elsewhere = Session("mario", path=str(tmp_path / "other" / "mario"))
    with pytest.raises(ValueError, match="not in the pool"):
        async with pool.open(elsewhere):
            pass


async def test_create_list_get_delete(tmp_path, chrome):
    pool = SessionPool(tmp_path / "pool")
    assert await pool.list() == []
    created = await pool.create("b", seed=7)
    await pool.create("a")
    assert created.seed == 7
    assert await pool.list() == ["a", "b"]
    assert (await pool.get("b")).seed == 7
    with pytest.raises(FileExistsError):
        await pool.create("b")
    await pool.delete("b")
    assert await pool.list() == ["a"]
    assert not os.path.exists(pool.path("b"))
    assert os.listdir(tmp_path / "pool") == ["a"]  # nothing left behind
    with pytest.raises(FileNotFoundError):
        await pool.delete("b")
    with pytest.raises(FileNotFoundError):
        await pool.get("b")


async def test_delete_of_a_session_open_in_the_pool_is_refused(tmp_path, chrome):
    pool = SessionPool(tmp_path)
    async with pool.open("a"):
        with pytest.raises(SessionBusyError) as info:
            await pool.delete("a")
        assert info.value.pid == os.getpid()
        assert os.path.isfile(os.path.join(pool.path("a"), "session.json"))
    await pool.delete("a")


async def test_delete_of_a_session_held_elsewhere_is_refused(tmp_path, chrome):
    pool = SessionPool(tmp_path)
    await pool.create("a")
    other = SessionLock(pool.path("a"))
    other.acquire()
    try:
        with pytest.raises(SessionBusyError) as info:
            await pool.delete("a")
        assert info.value.pid == os.getpid()
    finally:
        other.release()
    assert await pool.list() == ["a"]
    await pool.delete("a")
    assert await pool.list() == []


@pytest.mark.parametrize("name", ["", "../x", "a/b", ".hidden", "-x", "x" * 65])
async def test_bad_names_are_refused(tmp_path, chrome, name):
    pool = SessionPool(tmp_path)
    with pytest.raises(ValueError):
        pool.path(name)
    with pytest.raises(ValueError):
        await pool.create(name)
    with pytest.raises(ValueError):
        async with pool.open(name):
            pass


def test_max_browsers_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        SessionPool(tmp_path, max_browsers=0)
    with pytest.raises(TypeError):
        SessionPool(tmp_path, user_data_dir="x")


def test_the_directory_may_start_with_a_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    pool = SessionPool("~/sessions")
    assert pool.directory == str(tmp_path / "sessions")
    assert pool.path("a") == str(tmp_path / "sessions" / "a")
