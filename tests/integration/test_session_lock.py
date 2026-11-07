"""A session opens in one process at a time: the second gets SessionBusyError
with the PID (not a Chrome launch error), and a killed holder's lock comes back."""

from __future__ import annotations

import asyncio
import os

import pytest

from tellurium import Session, SessionBusyError
from tellurium.session.lock import SessionLock
from tests.integration.session_child import kill_holder, start_holder

_hold = start_holder
_kill_group = kill_holder


async def test_second_process_gets_busy_error_then_takes_the_lock_of_a_killed_one(tmp_path):
    path = str(tmp_path / "shared")
    holder = await _hold(path)
    try:
        session = Session("shared", path=path)
        with pytest.raises(SessionBusyError) as info:
            async with session.start(headless=True):
                pass
        assert info.value.pid == holder.pid
        assert SessionLock.holder(path) == holder.pid
    finally:
        holder.kill()  # the Python process only (SIGKILL, TerminateProcess): no cleanup runs
        await holder.wait()
    try:
        assert SessionLock.holder(path) is None
        async with session.start(headless=True) as browser:
            assert await browser.main_tab.eval("1 + 1") == 2
            assert SessionLock.holder(path) == os.getpid()
    finally:
        _kill_group(holder)  # an orphaned Chrome, if the kill left one
    assert SessionLock.holder(path) is None


async def test_two_sessions_on_one_folder_in_one_process(tmp_path):
    path = str(tmp_path / "s")
    async with Session("s", path=path).start(headless=True):
        with pytest.raises(SessionBusyError) as info:
            async with Session("s", path=path).start(headless=True):
                pass
        assert info.value.pid == os.getpid()
    async with Session("s", path=path).start(headless=True):
        pass


async def test_lock_is_released_when_the_body_raises(tmp_path):
    path = str(tmp_path / "s")
    with pytest.raises(ZeroDivisionError):
        async with Session("s", path=path).start(headless=True):
            assert SessionLock.holder(path) == os.getpid()
            raise ZeroDivisionError
    assert SessionLock.holder(path) is None


async def test_lock_is_released_when_the_launch_fails(tmp_path):
    path = str(tmp_path / "s")
    with pytest.raises(Exception):  # noqa: B017 - any launch error
        async with Session("s", path=path).start(headless=True, executable="/nonexistent"):
            pass
    assert SessionLock.holder(path) is None


async def test_lock_is_released_on_cancellation(tmp_path):
    path = str(tmp_path / "s")
    inside = asyncio.Event()

    async def run():
        async with Session("s", path=path).start(headless=True):
            inside.set()
            await asyncio.Event().wait()

    task = asyncio.ensure_future(run())
    await asyncio.wait_for(inside.wait(), 60)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert SessionLock.holder(path) is None


async def test_lock_is_held_while_chrome_launches(tmp_path, monkeypatch):
    """Taken before Chrome starts: the second opener never reaches Chrome."""
    import tellurium

    path = str(tmp_path / "s")
    seen = []
    real_launch = tellurium.Browser.launch

    async def spying_launch(**kwargs):
        seen.append(SessionLock.holder(path))
        return await real_launch(**kwargs)

    monkeypatch.setattr(tellurium.Browser, "launch", spying_launch)
    async with Session("s", path=path).start(headless=True):
        pass
    assert seen == [os.getpid()]


async def test_mcp_refuses_a_session_another_process_holds(tmp_path):
    pytest.importorskip("mcp")
    from tellurium.mcp.config import ServerConfig
    from tellurium.mcp.results import ToolError
    from tellurium.mcp.sessions import SessionPool

    config = ServerConfig(home=tmp_path)
    holder = await _hold(str(config.sessions_dir / "github"))
    try:
        async with SessionPool(config) as pool:
            with pytest.raises(ToolError, match=rf"another process \(PID {holder.pid}\)"):
                await pool.open("github")
            assert pool.sessions() == []
    finally:
        _kill_group(holder)
        await holder.wait()
