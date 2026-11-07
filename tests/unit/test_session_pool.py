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
    # Nothing left behind but the locks, beside the folders.
    assert sorted(os.listdir(tmp_path / "pool")) == [".a.lock", ".b.lock", "a"]
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
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # what Windows reads
    pool = SessionPool("~/sessions")
    assert pool.directory == str(tmp_path / "sessions")
    assert pool.path("a") == str(tmp_path / "sessions" / "a")


@pytest.mark.parametrize(
    "name", ["CON", "con", "nul", "Aux", "PRN", "COM1", "lpt9", "con.txt", "NUL.json", "a.", "a.."]
)
async def test_names_windows_cannot_hold_are_refused_everywhere(tmp_path, chrome, name):
    pool = SessionPool(tmp_path)
    with pytest.raises(ValueError):
        pool.path(name)
    with pytest.raises(ValueError):
        await pool.create(name)


@pytest.mark.parametrize("name", ["console", "com10", "nullable", "a.b", "a-.b_"])
async def test_names_close_to_reserved_ones_are_fine(tmp_path, chrome, name):
    pool = SessionPool(tmp_path)
    await pool.create(name)
    assert await pool.list() == [name]


async def test_a_name_differing_only_by_case_is_refused(tmp_path, chrome):
    pool = SessionPool(tmp_path)
    await pool.create("Alice")
    with pytest.raises(ValueError, match="Alice"):
        await pool.create("alice")
    with pytest.raises(ValueError, match="Alice"):
        await pool.get("ALICE")
    with pytest.raises(ValueError, match="Alice"):
        async with pool.open("alice"):
            pass
    with pytest.raises(ValueError, match="Alice"):
        await pool.delete("alice")
    assert await pool.list() == ["Alice"]
    assert chrome.started == []


async def test_names_differing_only_by_case_share_one_lock(tmp_path, chrome):
    pool = SessionPool(tmp_path)
    await pool.create("Alice")
    held = SessionLock(pool.path("Alice"))
    held.acquire()
    try:
        assert SessionLock.holder(os.path.join(str(tmp_path), "alice")) == os.getpid()
    finally:
        held.release()


async def test_a_name_that_is_a_symlink_is_refused_clearly(tmp_path, chrome):
    pool = SessionPool(tmp_path / "pool")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (tmp_path / "pool").mkdir()
    try:
        os.symlink(elsewhere, tmp_path / "pool" / "linked", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this system lets no unprivileged user make a symlink")
    for call in (pool.get, pool.delete, pool.create):
        with pytest.raises(ValueError, match="symlink"):
            await call("linked")
    with pytest.raises(ValueError, match="symlink"):
        async with pool.open("linked"):
            pass
    assert elsewhere.exists() and chrome.started == []


async def test_delete_renames_the_folder_with_its_lock_held(tmp_path, chrome, monkeypatch):
    """The lock is beside the folder, so the folder moves under it (Windows
    renames no folder with a file open inside)."""
    pool = SessionPool(tmp_path)
    await pool.create("a")
    held_at_rename = []
    real_rename = os.rename

    def rename(src, dst, *args, **kwargs):
        held_at_rename.append(SessionLock.holder(os.fspath(src)))
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "rename", rename)
    await pool.delete("a")
    assert held_at_rename == [os.getpid()]
    assert not os.listdir(tmp_path) or os.listdir(tmp_path) == [".a.lock"]


async def test_an_interrupted_delete_leaves_no_folder_behind(tmp_path, chrome, monkeypatch):
    pool = SessionPool(tmp_path)
    await pool.create("a")
    await pool.create("b")
    import shutil

    real_rmtree = shutil.rmtree

    def broken(path, *args, **kwargs):
        raise OSError("interrupted")

    monkeypatch.setattr(shutil, "rmtree", broken)
    with pytest.raises(OSError):
        await pool.delete("a")
    monkeypatch.setattr(shutil, "rmtree", real_rmtree)
    graves = [n for n in os.listdir(tmp_path) if ".deleted-" in n]
    assert graves  # what an interrupted delete leaves
    # The next delete clears it, and so does a pool opened afterwards.
    await pool.delete("b")
    assert [n for n in os.listdir(tmp_path) if ".deleted-" in n] == []
    os.mkdir(tmp_path / graves[0])
    (tmp_path / graves[0] / "cookies.json").write_text("{}")
    assert await SessionPool(tmp_path).list() == []
    assert [n for n in os.listdir(tmp_path) if ".deleted-" in n] == []


async def test_a_delete_that_cannot_remove_the_folder_says_so(
    tmp_path, chrome, monkeypatch, caplog
):
    """The identity is gone, but its folder (cookies included) is still on disk:
    a warning names it, and the next pool removes it."""
    pool = SessionPool(tmp_path)
    await pool.create("a")
    import shutil

    real_rmtree = shutil.rmtree

    def refused(path, ignore_errors=False, *args, **kwargs):
        if not ignore_errors:
            raise PermissionError("in use")

    monkeypatch.setattr(shutil, "rmtree", refused)
    with caplog.at_level("WARNING", logger="tellurium"):
        await pool.delete("a")
    assert await pool.list() == []
    graves = [n for n in os.listdir(tmp_path) if ".deleted-" in n]
    assert graves
    assert any(graves[0] in r.getMessage() for r in caplog.records)
    monkeypatch.setattr(shutil, "rmtree", real_rmtree)
    assert await SessionPool(tmp_path).list() == []
    assert [n for n in os.listdir(tmp_path) if ".deleted-" in n] == []


async def test_a_folder_whose_name_is_no_longer_valid_is_left_out_with_a_warning(
    tmp_path, chrome, caplog
):
    """A pool made before the portable names (``CON``, ``a.``) keeps those
    folders out of list(), but says which and why."""
    pool = SessionPool(tmp_path)
    await pool.create("ok")
    os.mkdir(tmp_path / "CON.x")
    os.mkdir(tmp_path / ".hidden")  # not a session: no warning
    with caplog.at_level("WARNING", logger="tellurium"):
        assert await pool.list() == ["ok"]
    messages = [r.getMessage() for r in caplog.records]
    assert any("'CON.x'" in m for m in messages)
    assert not any(".hidden" in m for m in messages)
