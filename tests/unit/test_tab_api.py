"""Tab API surface promised by design doc 03: xpath_all, pdf, viewport, waits."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from tellurium.browser.tab import Tab, url_matches


def _fake_tab(*, responses=None, mouse_profile="normal"):
    """Tab backed by a mock session + a mock browser router root."""
    sent: list[tuple[str, dict]] = []
    root_sent: list[tuple[str, dict]] = []
    responses = responses or {}

    async def _send(method, params=None, timeout=None):
        sent.append((method, params or {}))
        value = responses.get(method, {})
        return value(params or {}) if callable(value) else value

    async def _root_send(method, params=None, timeout=None):
        root_sent.append((method, params or {}))
        value = responses.get(method, {})
        return value(params or {}) if callable(value) else value

    session = MagicMock()
    session.send = AsyncMock(side_effect=_send)
    session.on = MagicMock()

    browser = MagicMock()
    browser._router.root.send = AsyncMock(side_effect=_root_send)
    browser._stealth_engine = None
    browser._stealth_profile = None

    tab = Tab(session, browser, "T1", mouse_profile=mouse_profile)
    tab._sent = sent
    tab._root_sent = root_sent
    return tab


def _methods(pairs):
    return [m for m, _ in pairs]


# ---------------------------------------------------------------------------
# mouse_profile
# ---------------------------------------------------------------------------


def test_tab_rejects_unknown_mouse_profile():
    with pytest.raises(ValueError, match="mouse_profile"):
        _fake_tab(mouse_profile="reckless")


async def test_mouse_move_uses_the_tabs_profile(monkeypatch):
    from tellurium.browser import tab as tab_mod

    tab = _fake_tab(mouse_profile="hasty")
    seen: dict = {}

    import tellurium.stealth.human as human

    real_wind = human.wind_mouse

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real_wind(*args, **kwargs)

    monkeypatch.setattr(human, "wind_mouse", spy)
    tab._ensure_screen_parity = AsyncMock()
    await tab.mouse_move(40, 40, human=True)
    assert seen == human.MOUSE_PROFILES["hasty"]["wind"]
    assert tab_mod is not None  # module imported cleanly


# ---------------------------------------------------------------------------
# select_all / find_all / xpath_all timeouts
# ---------------------------------------------------------------------------


async def test_select_all_returns_immediately_without_timeout():
    tab = _fake_tab(
        responses={
            "DOM.getDocument": {"root": {"nodeId": 1}},
            "DOM.querySelectorAll": {"nodeIds": []},
        }
    )
    assert await tab.select_all(".missing") == []
    assert _methods(tab._sent).count("DOM.querySelectorAll") == 1


async def test_select_all_polls_until_a_match_appears():
    calls = {"n": 0}

    def query(_params):
        calls["n"] += 1
        return {"nodeIds": [11, 12]} if calls["n"] >= 2 else {"nodeIds": []}

    tab = _fake_tab(
        responses={
            "DOM.getDocument": {"root": {"nodeId": 1}},
            "DOM.querySelectorAll": query,
            "DOM.resolveNode": lambda p: {"object": {"objectId": f"OBJ{p['nodeId']}"}},
        }
    )
    elements = await tab.select_all("li", timeout=5)
    assert [e._object_id for e in elements] == ["OBJ11", "OBJ12"]
    assert calls["n"] == 2


async def test_find_all_accepts_a_timeout():
    tab = _fake_tab()
    tab._find_text_elements = AsyncMock(return_value=[])
    assert await tab.find_all("nope", timeout=0.3) == []
    assert tab._find_text_elements.await_count >= 2


async def test_xpath_all_returns_every_match_and_discards_results():
    tab = _fake_tab(
        responses={
            "DOM.getDocument": {"root": {"nodeId": 1}},
            "DOM.performSearch": {"searchId": "S1", "resultCount": 3},
            "DOM.getSearchResults": {"nodeIds": [4, 5, 6]},
            "DOM.resolveNode": lambda p: {"object": {"objectId": f"OBJ{p['nodeId']}"}},
        }
    )
    elements = await tab.xpath_all("//li")
    assert [e._object_id for e in elements] == ["OBJ4", "OBJ5", "OBJ6"]
    search = dict(tab._sent)["DOM.getSearchResults"]
    assert search == {"searchId": "S1", "fromIndex": 0, "toIndex": 3}
    assert ("DOM.discardSearchResults", {"searchId": "S1"}) in tab._sent


async def test_xpath_all_empty_result_is_not_an_error():
    tab = _fake_tab(
        responses={
            "DOM.getDocument": {"root": {"nodeId": 1}},
            "DOM.performSearch": {"searchId": "S1", "resultCount": 0},
        }
    )
    assert await tab.xpath_all("//nothing") == []
    assert ("DOM.discardSearchResults", {"searchId": "S1"}) in tab._sent


# ---------------------------------------------------------------------------
# wait_for states
# ---------------------------------------------------------------------------


def _wait_for_tab(node_ids, visible=True):
    """Tab whose querySelector walks *node_ids* one call at a time."""
    remaining = list(node_ids)

    def query(_params):
        nid = remaining.pop(0) if remaining else 0
        return {"nodeId": nid}

    tab = _fake_tab(
        responses={
            "DOM.getDocument": {"root": {"nodeId": 1}},
            "DOM.querySelector": query,
            "DOM.resolveNode": {"object": {"objectId": "OBJ"}},
            "Runtime.callFunctionOn": {"result": {"type": "boolean", "value": visible}},
        }
    )
    return tab


async def test_wait_for_visible_returns_the_element():
    tab = _wait_for_tab([0, 9], visible=True)
    element = await tab.wait_for("#late", timeout=5)
    assert element is not None and element._node_id == 9
    assert element._selector == "#late"


async def test_wait_for_attached_does_not_check_visibility():
    tab = _wait_for_tab([9], visible=False)
    element = await tab.wait_for("#x", state="attached", timeout=5)
    assert element._node_id == 9
    assert "Runtime.callFunctionOn" not in _methods(tab._sent)


async def test_wait_for_hidden_accepts_an_invisible_element():
    tab = _wait_for_tab([9], visible=False)
    assert await tab.wait_for("#x", state="hidden", timeout=5) is None


async def test_wait_for_detached_waits_for_the_node_to_go_away():
    tab = _wait_for_tab([9, 0], visible=True)
    assert await tab.wait_for("#x", state="detached", timeout=5) is None


async def test_wait_for_times_out():
    tab = _wait_for_tab([], visible=True)
    with pytest.raises(TimeoutError):
        await tab.wait_for("#never", timeout=0.3)


async def test_wait_for_rejects_an_unknown_state():
    tab = _fake_tab()
    with pytest.raises(ValueError, match="state"):
        await tab.wait_for("#x", state="sideways")


# ---------------------------------------------------------------------------
# URL matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pattern,url,expected",
    [
        ("*/dashboard*", "https://x.test/app/dashboard?a=1", True),
        ("*/dashboard*", "https://x.test/app/settings", False),
        ("https://x.test/?", "https://x.test/a", True),
        ("/dashboard", "https://x.test/app/dashboard", True),  # substring compat
        ("/dashboard", "https://x.test/app/settings", False),
        ("*", "", False),
    ],
)
def test_url_matches(pattern, url, expected):
    assert url_matches(pattern, url) is expected


async def test_wait_for_url_uses_glob():
    tab = _fake_tab()
    tab.eval = AsyncMock(return_value="https://x.test/app/dashboard?a=1")
    await tab.wait_for_url("*/dashboard*", timeout=1)
    assert tab.url == "https://x.test/app/dashboard?a=1"


async def test_wait_for_url_glob_that_never_matches_times_out():
    tab = _fake_tab()
    tab.eval = AsyncMock(return_value="https://x.test/login")
    with pytest.raises(TimeoutError):
        await tab.wait_for_url("*/dashboard*", timeout=0.3)


# ---------------------------------------------------------------------------
# pdf / screenshot
# ---------------------------------------------------------------------------


async def test_pdf_returns_bytes_and_writes_the_file(tmp_path):
    payload = b"%PDF-1.4 fake"
    tab = _fake_tab(
        responses={
            "Page.printToPDF": {"data": base64.b64encode(payload).decode()},
        }
    )
    out = tmp_path / "page.pdf"
    data = await tab.pdf(str(out), landscape=True, paperWidth=8.5)
    assert data == payload
    assert out.read_bytes() == payload
    params = dict(tab._sent)["Page.printToPDF"]
    assert params["landscape"] is True
    assert params["paperWidth"] == 8.5
    assert params["printBackground"] is True


async def test_pdf_without_path_only_returns_bytes():
    tab = _fake_tab(responses={"Page.printToPDF": {"data": base64.b64encode(b"x").decode()}})
    assert await tab.pdf() == b"x"


async def test_screenshot_quality_is_sent_for_jpeg():
    tab = _fake_tab(
        responses={
            "Page.captureScreenshot": {"data": base64.b64encode(b"jpg").decode()},
        }
    )
    await tab.screenshot(format="jpeg", quality=40)
    assert dict(tab._sent)["Page.captureScreenshot"] == {"format": "jpeg", "quality": 40}


async def test_screenshot_quality_is_dropped_for_png(caplog):
    tab = _fake_tab(
        responses={
            "Page.captureScreenshot": {"data": base64.b64encode(b"png").decode()},
        }
    )
    with caplog.at_level("WARNING", logger="tellurium"):
        await tab.screenshot(quality=40)
    assert "quality" not in dict(tab._sent)["Page.captureScreenshot"]
    assert "quality" in caplog.text


# ---------------------------------------------------------------------------
# Window control
# ---------------------------------------------------------------------------


async def test_set_viewport_prefers_set_window_bounds():
    tab = _fake_tab(responses={"Browser.getWindowForTarget": {"windowId": 3}})
    await tab.set_viewport(1024, 768)
    assert (
        "Browser.setWindowBounds",
        {
            "windowId": 3,
            "bounds": {"width": 1024, "height": 768, "windowState": "normal"},
        },
    ) in tab._root_sent
    assert "Emulation.setDeviceMetricsOverride" not in _methods(tab._sent)


async def test_set_viewport_falls_back_to_device_metrics_with_a_warning(caplog):
    tab = _fake_tab()
    tab._browser._router.root.send = AsyncMock(side_effect=RuntimeError("not supported"))
    with caplog.at_level("WARNING", logger="tellurium"):
        await tab.set_viewport(800, 600)
    assert "setDeviceMetricsOverride" in caplog.text
    params = dict(tab._sent)["Emulation.setDeviceMetricsOverride"]
    assert params["width"] == 800 and params["height"] == 600


async def test_maximize_and_minimize_send_window_state():
    tab = _fake_tab(responses={"Browser.getWindowForTarget": {"windowId": 3}})
    await tab.maximize()
    await tab.minimize()
    states = [
        p["bounds"]["windowState"] for m, p in tab._root_sent if m == "Browser.setWindowBounds"
    ]
    assert states == ["maximized", "minimized"]


async def test_window_bounds_change_invalidates_the_screen_offset():
    tab = _fake_tab(responses={"Browser.getWindowForTarget": {"windowId": 3}})
    tab._screen_offset = (10.0, 20.0)
    await tab.maximize()
    assert tab._screen_offset is None


async def test_bring_to_front():
    tab = _fake_tab()
    await tab.bring_to_front()
    assert ("Page.bringToFront", {}) in tab._sent


# ---------------------------------------------------------------------------
# Typing with typos
# ---------------------------------------------------------------------------


async def test_keyboard_type_typos_requires_human():
    tab = _fake_tab()
    with pytest.raises(ValueError, match="human=True"):
        await tab.keyboard_type("abc", typos=True)


async def test_named_keys_are_dispatched_without_text(monkeypatch):
    """A Backspace from the typo simulation must not insert the literal word."""
    import tellurium.stealth.human as human

    tab = _fake_tab()
    tab._human_action = AsyncMock()

    class _AlwaysTypo:
        def random(self):
            return 0.0

        def choice(self, seq):
            return seq[0]

    tab._typo_rng = _AlwaysTypo()
    monkeypatch.setattr(human.HumanTyping, "_compute_iki", lambda *a, **k: 0.0)
    monkeypatch.setattr(human.HumanTyping, "_compute_dwell", lambda *a, **k: 0.0)
    await tab.keyboard_type("a", human=True, typos=True, wpm=10_000)

    key_events = [p for m, p in tab._sent if m == "Input.dispatchKeyEvent"]
    backspaces = [p for p in key_events if p.get("key") == "Backspace"]
    assert backspaces, "expected a Backspace correction"
    assert all("text" not in p for p in backspaces)
    assert all(p["windowsVirtualKeyCode"] == 8 for p in backspaces)
    assert {p["type"] for p in backspaces} == {"keyDown", "keyUp"}


# ---------------------------------------------------------------------------
# Downloads accessor
# ---------------------------------------------------------------------------


def test_browser_exposes_its_downloads():
    from tellurium.browser.browser import Browser
    from tellurium.browser.download import Downloads

    browser = Browser()
    assert isinstance(browser.downloads, Downloads)
    assert browser.downloads is browser.downloads


def test_expect_download_goes_through_the_browser_accessor():
    tab = _fake_tab()
    downloads = MagicMock()
    tab._browser = MagicMock(spec=["downloads"], downloads=downloads)
    waiter = tab.expect_download(timeout=5)
    downloads.expect_frames.assert_called_once_with(tab._frames, timeout=5)
    assert waiter is downloads.expect_frames.return_value
