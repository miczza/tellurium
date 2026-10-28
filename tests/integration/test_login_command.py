"""``tellurium login``: a headed window on a named session; when the person
closes it the session is saved (``session.json``, ``cookies.json``) and the MCP
server opens it signed in, the cookie with no expiry included."""

from __future__ import annotations

import asyncio
import json
import os

import pytest

import tellurium
from tellurium.session import login_command
from tests.integration.test_wait_for_human import _click_node, _done_button

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs a display (xvfb-run)")


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
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not launched:
        assert loop.time() < deadline, "no browser launched"
        await asyncio.sleep(0.05)
    return launched[0]


async def _cookie(browser, name, timeout=15.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if any(c.name == name for c in await browser.get_cookies()):
            return
        assert loop.time() < deadline, f"no {name} cookie"
        await asyncio.sleep(0.1)


async def _loaded(tab, page, timeout=15.0):
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


async def _close_windows(browser) -> None:
    """What the person does: close every window (Chrome stays up for the save)."""
    root = browser._router.root
    targets = (await root.send("Target.getTargets", {}, timeout=5))["targetInfos"]
    for t in targets:
        if t["type"] == "page":
            await root.send("Target.closeTarget", {"targetId": t["targetId"]}, timeout=5)


async def test_closing_the_window_saves_a_session_mcp_reopens_signed_in(
    tmp_path, local_server, launched
):
    pytest.importorskip("mcp")
    from tellurium.mcp.config import ServerConfig
    from tellurium.mcp.sessions import SessionPool

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
        await _close_windows(browser)
        path = await asyncio.wait_for(task, 30)
    finally:
        task.cancel()
    folder = config.sessions_dir / "acct"
    assert path == str(folder)
    assert json.loads((folder / "session.json").read_text())["name"] == "acct"
    saved = json.loads((folder / "cookies.json").read_text())["cookies"]
    assert any(c["name"] == "http_sso" and c["expires"] == -1 for c in saved)
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
        await asyncio.wait_for(task, 30)
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
        await root.send("Target.closeTarget", {"targetId": tab._target_id}, timeout=5)
        await asyncio.wait_for(task, 30)
    finally:
        task.cancel()
    saved = json.loads((tmp_path / "acct" / "cookies.json").read_text())["cookies"]
    assert any(c["name"] == "late" and c["expires"] == -1 for c in saved)
