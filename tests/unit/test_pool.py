"""SessionPool over the real Session.start, with Browser.launch faked: the pool
outlives an event loop, open(create=False) never makes an identity, and an
identity removed while its open waits for a slot keeps its seed."""

from __future__ import annotations

import asyncio
import json
import os
import shutil

import pytest

import tellurium
from tellurium.session import SessionPool


class _FakeBrowser:
    def __init__(self, seed):
        self.seed = seed
        self.main_tab = object()

    async def get_cookies(self, domain=None):
        return []

    async def set_cookies(self, cookies):
        pass

    async def close(self):
        pass


@pytest.fixture
def launched(monkeypatch):
    """The keyword arguments of each Browser.launch."""
    seen: list[dict] = []

    async def launch(**kwargs):
        seen.append(kwargs)
        return _FakeBrowser(kwargs.get("seed"))

    monkeypatch.setattr(tellurium.Browser, "launch", launch)
    return seen


def test_the_pool_works_in_one_asyncio_run_after_another(tmp_path, launched):
    pool = SessionPool(tmp_path, max_browsers=1)

    async def use(name):
        async def hold(n):
            async with pool.open(n):
                await asyncio.sleep(0.01)

        # Two at once on one slot: the second waits on the semaphore.
        await asyncio.wait_for(asyncio.gather(hold(name), hold(name + "-2")), 10)

    asyncio.run(use("a"))
    asyncio.run(use("b"))
    assert len(launched) == 4


async def test_open_without_create_refuses_a_missing_identity(tmp_path, launched):
    pool = SessionPool(tmp_path)
    with pytest.raises(FileNotFoundError, match="ghost"):
        async with pool.open("ghost", create=False):
            pass
    assert launched == []
    assert not os.path.exists(pool.path("ghost"))


async def test_open_without_create_opens_an_existing_identity(tmp_path, launched):
    pool = SessionPool(tmp_path)
    await pool.create("mario", seed=42)
    async with pool.open("mario", create=False):
        pass
    assert launched[0]["seed"] == 42


async def _removed_while_waiting(pool, launched, **open_kwargs):
    """Open "b" while "a" holds the only slot; remove b's folder (another
    process deleting it) before the slot frees up."""
    async with pool.open("a"):
        waiting = asyncio.create_task(_open_b(pool, **open_kwargs))
        while not os.path.exists(os.path.join(pool.path("b"), "session.json")):
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # b is on the semaphore now
        shutil.rmtree(pool.path("b"))
    return await asyncio.wait_for(waiting, 10)


async def _open_b(pool, **open_kwargs):
    async with pool.open("b", **open_kwargs) as browser:
        return browser.seed


async def test_an_identity_removed_while_waiting_for_a_slot_keeps_its_seed(tmp_path, launched):
    pool = SessionPool(tmp_path, max_browsers=1)
    await pool.create("b", seed=77)
    assert await _removed_while_waiting(pool, launched) == 77
    with open(os.path.join(pool.path("b"), "session.json")) as f:
        assert json.load(f)["seed"] == 77  # the next open has the same fingerprint


async def test_without_create_an_identity_removed_while_waiting_is_not_reborn(tmp_path, launched):
    pool = SessionPool(tmp_path, max_browsers=1)
    await pool.create("b", seed=77)
    with pytest.raises(FileNotFoundError):
        await _removed_while_waiting(pool, launched, create=False)
    assert len(launched) == 1  # only a's Chrome
    assert await pool.list() == ["a"]


async def test_the_lock_file_is_never_removed_while_held(tmp_path, launched, monkeypatch):
    """The folder the start's lock made again is cleared only after the lock is
    let go and taken anew, by moving the folder away: a lock file removed while
    held would let another process lock a new one beside it."""
    pool = SessionPool(tmp_path, max_browsers=1)
    await pool.create("b", seed=77)
    lock_file = os.path.join(pool.path("b"), "session.lock")
    removed: list[str] = []
    real_unlink = os.unlink

    def spying_unlink(path, *args, **kwargs):
        removed.append(os.fspath(path))
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", spying_unlink)
    monkeypatch.setattr(os, "remove", spying_unlink)
    with pytest.raises(FileNotFoundError):
        await _removed_while_waiting(pool, launched, create=False)
    assert lock_file not in removed
    assert await pool.list() == ["a"]


def test_the_cap_holds_across_loops_running_at_once_in_threads(tmp_path, monkeypatch):
    """Three threads, each with its own asyncio.run: still one browser at a time."""
    import threading

    guard = threading.Lock()
    count = {"now": 0, "peak": 0}

    class _Counted(_FakeBrowser):
        async def close(self):
            with guard:
                count["now"] -= 1

    async def launch(**kwargs):
        with guard:
            count["now"] += 1
            count["peak"] = max(count["peak"], count["now"])
        return _Counted(kwargs.get("seed"))

    monkeypatch.setattr(tellurium.Browser, "launch", launch)
    pool = SessionPool(tmp_path, max_browsers=1)
    errors: list[BaseException] = []

    def run(k):
        async def opens():
            async def one(i):
                async with pool.open(f"t{k}-{i}"):
                    await asyncio.sleep(0.02)

            await asyncio.wait_for(asyncio.gather(*(one(i) for i in range(5))), 30)

        try:
            asyncio.run(opens())
        except BaseException as exc:  # noqa: BLE001 - collected for the assert
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(k,)) for k in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert count == {"now": 0, "peak": 1}
