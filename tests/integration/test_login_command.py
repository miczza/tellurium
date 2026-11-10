"""``tellurium login``: a headed window on a named session; when the person
closes it the session is saved (``session.json``, ``cookies.json``) and the MCP
server opens it signed in, the cookie with no expiry included."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

import tellurium
from tellurium.session import login_command, session_cookies
from tests.integration import banner_probe
from tests.integration.login_timeline import LoginTimeline
from tests.integration.test_wait_for_human import _click_node, _done_button
from tests.platform_marks import needs_display
from tests.timeout_scale import scaled

pytestmark = needs_display


@pytest.fixture
def launched(monkeypatch):
    """The browsers Browser.launch returns, as they come."""
    seen: list = []
    real_launch = tellurium.Browser.launch

    async def spying_launch(**kwargs):
        browser = await real_launch(**kwargs)
        seen.append(browser)
        return browser

    monkeypatch.setattr(tellurium.Browser, "launch", spying_launch)
    return seen


async def _first(launched, timeout=30.0):
    timeout = scaled(timeout)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not launched:
        assert loop.time() < deadline, "no browser launched"
        await asyncio.sleep(0.05)
    return launched[0]


async def _cookie(browser, name, timeout=15.0):
    timeout = scaled(timeout)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if any(c.name == name for c in await browser.get_cookies()):
            return
        assert loop.time() < deadline, f"no {name} cookie"
        await asyncio.sleep(0.1)


async def _loaded(tab, page, timeout=15.0):
    timeout = scaled(timeout)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        try:
            href = await tab.eval("document.readyState === 'complete' && location.href")
        except Exception:  # noqa: BLE001 - mid-navigation
            href = None
        if href and page in href:
            return
        assert loop.time() < deadline, f"{page} never loaded"
        await asyncio.sleep(0.1)


async def _close_windows(browser, timeline=None) -> None:
    """What the person does: close every window (Chrome stays up for the save)."""
    root = browser._router.root
    targets = (await root.send("Target.getTargets", {}, timeout=scaled(5)))["targetInfos"]
    for t in targets:
        if t["type"] == "page":
            if timeline is not None:
                timeline.note(f"test closes {timeline._name(t['targetId'])}")
            await root.send("Target.closeTarget", {"targetId": t["targetId"]}, timeout=scaled(5))


async def test_closing_the_window_saves_a_session_mcp_reopens_signed_in(
    tmp_path, local_server, launched, monkeypatch
):
    pytest.importorskip("mcp")
    from tellurium.mcp.config import ServerConfig
    from tellurium.mcp.sessions import SessionPool

    timeline = LoginTimeline(monkeypatch, "http_sso")
    config = ServerConfig(home=tmp_path)
    task = asyncio.create_task(
        login_command.login(
            "acct", f"{local_server}/session-cookie", directory=str(config.sessions_dir)
        )
    )
    try:
        browser = await _first(launched)
        await _cookie(browser, "http_sso")
        await asyncio.sleep(4 * login_command.POLL)  # a cookie that old is never missed
        await _close_windows(browser, timeline)
        path = await asyncio.wait_for(task, scaled(30))
    finally:
        task.cancel()
    folder = config.sessions_dir / "acct"
    assert path == str(folder)
    assert json.loads((folder / "session.json").read_text())["name"] == "acct"
    saved = json.loads((folder / "cookies.json").read_text())["cookies"]
    assert any(c["name"] == "http_sso" and c["expires"] == -1 for c in saved), timeline
    if sys.platform != "win32":  # no POSIX modes there (an ACL would be needed)
        assert (folder / "cookies.json").stat().st_mode & 0o777 == 0o600

    async with SessionPool(config) as pool:
        opened, _ = await pool.open("acct")
        jar = await opened.browser.get_cookies()
        assert any(c.name == "http_sso" and c.value == "1" for c in jar)


async def test_done_on_the_banner_ends_the_login_too(tmp_path, local_server, launched):
    task = asyncio.create_task(
        login_command.login("acct", f"{local_server}/basic.html", directory=str(tmp_path))
    )
    try:
        browser = await _first(launched)
        tab = browser.main_tab
        await _click_node(tab, await _done_button(tab))
        done, _ = await asyncio.wait({task}, timeout=scaled(30))
        assert done, await banner_probe.report(tab)
        await task
    finally:
        task.cancel()
    assert (tmp_path / "acct" / "session.json").exists()
    assert (tmp_path / "acct" / "cookies.json").exists()


async def test_a_cookie_set_just_before_the_window_closes_is_saved(
    tmp_path, local_server, launched
):
    """A session cookie (no expiry) written 50 ms before the person closes the
    sign-in window: Chrome drops those with its last window, so it is kept
    open by another one of its own until the jar has been saved."""
    task = asyncio.create_task(
        login_command.login("acct", f"{local_server}/basic.html", directory=str(tmp_path))
    )
    try:
        browser = await _first(launched)
        tab = browser.main_tab
        await _loaded(tab, "basic.html")
        await tab.eval("document.cookie = 'late=1; path=/'")
        await asyncio.sleep(0.05)
        root = browser._router.root
        await root.send("Target.closeTarget", {"targetId": tab._target_id}, timeout=scaled(5))
        await asyncio.wait_for(task, scaled(30))
    finally:
        task.cancel()
    saved = json.loads((tmp_path / "acct" / "cookies.json").read_text())["cookies"]
    assert any(c["name"] == "late" and c["expires"] == -1 for c in saved)


async def test_session_cookies_chrome_drops_after_the_windows_went_are_saved(
    tmp_path, local_server, launched, monkeypatch
):
    """Chrome ends its browsing session a moment after its last window has
    gone from the targets (on Windows, long enough to be seen): the cookies
    with no expiry vanish from the jar later than that. The jar read while a
    window was open still reaches cookies.json."""
    real_windows_closed = login_command._windows_closed

    async def windows_closed_then_late_drop(browser, keeper):
        kept = await real_windows_closed(browser, keeper)
        await browser.clear_cookies()  # what Chrome does, late
        return kept

    monkeypatch.setattr(login_command, "_windows_closed", windows_closed_then_late_drop)
    task = asyncio.create_task(
        login_command.login("acct", f"{local_server}/session-cookie", directory=str(tmp_path))
    )
    try:
        browser = await _first(launched)
        await _cookie(browser, "http_sso")
        await asyncio.sleep(4 * login_command.POLL)  # a cookie that old is never missed
        await _close_windows(browser)
        await asyncio.wait_for(task, scaled(30))
    finally:
        task.cancel()
    saved = json.loads((tmp_path / "acct" / "cookies.json").read_text())["cookies"]
    assert any(c["name"] == "http_sso" and c["expires"] == -1 for c in saved)


async def test_the_login_cookies_are_written_under_the_session_lock(
    tmp_path, local_server, launched, monkeypatch
):
    """The jar read while a window was open goes to cookies.json before the
    session lets its lock go: another process opening the session (or a delete)
    right after the login never sees the file without them, nor has it rewritten."""
    from tellurium.session.lock import SessionLock

    real_windows_closed = login_command._windows_closed

    async def windows_closed_then_late_drop(browser, keeper):
        kept = await real_windows_closed(browser, keeper)
        await browser.clear_cookies()  # Chrome drops the cookies with no expiry, late
        return kept

    folder = str(tmp_path / "acct")
    writes: list[tuple[bool, bool]] = []  # (has the login's cookie, lock held)
    real_save = session_cookies.save

    def watched_save(path, cookies, *, at_close=False):
        if os.path.normpath(path) == os.path.normpath(folder):
            has = any(c.name == "http_sso" for c in cookies)
            writes.append((has, SessionLock.holder(folder) is not None))
        real_save(path, cookies, at_close=at_close)

    monkeypatch.setattr(login_command, "_windows_closed", windows_closed_then_late_drop)
    monkeypatch.setattr(session_cookies, "save", watched_save)
    task = asyncio.create_task(
        login_command.login("acct", f"{local_server}/session-cookie", directory=str(tmp_path))
    )
    try:
        browser = await _first(launched)
        await _cookie(browser, "http_sso")
        await asyncio.sleep(4 * login_command.POLL)  # a cookie that old is never missed
        await _close_windows(browser)
        await asyncio.wait_for(task, scaled(30))
    finally:
        task.cancel()
    assert writes and writes[-1][0]  # the last write has the login's cookie
    assert all(held for _, held in writes)
    saved = json.loads((tmp_path / "acct" / "cookies.json").read_text())["cookies"]
    assert any(c["name"] == "http_sso" and c["expires"] == -1 for c in saved)


async def test_the_keeper_closing_just_after_the_sign_in_window_keeps_the_cookies(
    tmp_path, local_server, launched, monkeypatch
):
    """The person closes both windows; on Windows the keeper's can still be
    listed when the other has gone, so the login ends with the keeper "open",
    and Chrome drops the cookies with no expiry before the session's close
    reads its jar. The jar read while the sign-in window was open saves them."""
    timeline = LoginTimeline(monkeypatch, "http_sso")
    watch = login_command._windows_closed  # the timeline's

    async def keeper_closed_then_dropped(browser, keeper):
        kept = await watch(browser, keeper)
        root = browser._router.root
        await root.send("Target.closeTarget", {"targetId": keeper}, timeout=scaled(5))
        await browser.clear_cookies()  # Chrome ends its browsing session
        timeline.note("keeper closed, jar dropped")
        return kept

    monkeypatch.setattr(login_command, "_windows_closed", keeper_closed_then_dropped)
    task = asyncio.create_task(
        login_command.login("acct", f"{local_server}/session-cookie", directory=str(tmp_path))
    )
    try:
        browser = await _first(launched)
        await _cookie(browser, "http_sso")
        await asyncio.sleep(4 * login_command.POLL)  # a cookie that old is never missed
        await browser.main_tab.close()  # the sign-in window; the keeper stays listed
        await asyncio.wait_for(task, scaled(30))
    finally:
        task.cancel()
    saved = json.loads((tmp_path / "acct" / "cookies.json").read_text())["cookies"]
    assert any(c["name"] == "http_sso" and c["expires"] == -1 for c in saved), timeline
