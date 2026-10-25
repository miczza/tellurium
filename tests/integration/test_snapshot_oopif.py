"""A2 part C — cross-site iframes (OOPIFs) in the snapshot, refs and clicks.

The host page is served from 127.0.0.1 and its login widget from localhost: two
sites for Chrome, so the widget runs in its own renderer (checked below). Its
"Sign in" button sits at (10, 10) of the widget, which in host coordinates is a
"Delete account" button: a click computed in the wrong frame lands there.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from tellurium.browser.geometry import ElementNotHittableError, content_box
from tellurium.browser.handles import StaleElementError

# The <iframe> of oopif_host.html: left/top 360/140, border 4, padding 6.
_WIDGET_ORIGIN = (370, 150)


def _ref_of(text: str, line_start: str) -> str:
    for line in text.splitlines():
        if line.strip().startswith(line_start):
            match = re.search(r"\[ref=(e\d+)\]", line)
            assert match, line
            return match.group(1)
    raise AssertionError(f"no line starting with {line_start!r} in:\n{text}")


async def _snapshot_with(tab, needle: str, **kw) -> str:
    """The snapshot once *needle* shows (frames commit after the host's load)."""
    text = ""
    for _ in range(50):
        text = await tab.snapshot(**kw)
        if needle in text:
            return text
        await asyncio.sleep(0.1)
    raise AssertionError(f"{needle!r} never showed in:\n{text}")


async def _iframe_targets(tab) -> list[str]:
    infos = (await tab._session._router.root.send("Target.getTargets", {}))["targetInfos"]
    return [info["url"] for info in infos if info["type"] == "iframe"]


async def _open(tab, local_server: str, query: str = "") -> None:
    await tab.get(f"{local_server}/oopif_host.html{query}")


async def test_localhost_widget_is_an_oopif(browser, local_server):
    tab = browser.main_tab
    await _open(tab, local_server)
    await _snapshot_with(tab, "Sign in")
    port = local_server.rsplit(":", 1)[1]
    assert f"http://localhost:{port}/oopif_login.html" in await _iframe_targets(tab)


async def test_snapshot_stitches_the_oopif_content(any_browser, local_server):
    tab = any_browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, '- button "Sign in" [ref=')
    assert "[oopif]" not in text
    assert '- iframe "Login" [ref=' in text
    assert '- textbox "Email" [ref=' in text
    assert re.search(r'- paragraph \[ref=e\d+\]: "signed out"', text)
    # the widget's nodes sit under the iframe line, one level deeper
    lines = text.splitlines()
    frame = next(i for i, line in enumerate(lines) if line.startswith('- iframe "Login"'))
    assert lines[frame + 1].startswith('  - button "Sign in"')
    interactive = await tab.snapshot(interactive=True)
    assert '- button "Sign in" [ref=' in interactive and "iframe" not in interactive


async def test_stealth_reuses_the_auto_attached_session(stealth_browser, local_server):
    """Attaching a second session would let the engine patch the frame twice."""
    tab = stealth_browser.main_tab
    await _open(tab, local_server)
    await _snapshot_with(tab, "Sign in")
    await _open(tab, local_server)  # a new widget, a new frame
    await _snapshot_with(tab, "Sign in")
    router, port = tab._session._router, local_server.rsplit(":", 1)[1]
    targets = (await router.root.send("Target.getTargets", {}))["targetInfos"]
    (widget,) = [t for t in targets if t["url"].startswith(f"http://localhost:{port}")]
    on_widget = 0
    for session in [s for s in router._sessions.values() if s is not router.root]:
        try:
            info = await session.send("Target.getTargetInfo", {}, timeout=5)
        except Exception:  # noqa: BLE001 — a worker or a closing target
            continue
        on_widget += info["targetInfo"]["targetId"] == widget["targetId"]
    assert on_widget == 1


async def test_oopif_refs_are_stable_and_distinct_from_the_host(browser, local_server):
    tab = browser.main_tab
    await _open(tab, local_server)
    first = await _snapshot_with(tab, "Sign in")
    second = await tab.snapshot()
    assert _ref_of(first, '- button "Sign in"') == _ref_of(second, '- button "Sign in"')
    refs = re.findall(r"\[ref=(e\d+)\]", second)
    assert len(refs) == len(set(refs))  # backend ids repeat across renderers, refs do not


async def test_oopif_refs_fill_and_click(any_browser, local_server):
    tab = any_browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    email = await tab.ref(_ref_of(text, '- textbox "Email"'))
    await email.type("ada@example.com")
    await (await tab.ref(_ref_of(text, '- button "Sign in"'))).click()
    after = await tab.snapshot()
    assert '"signed in as ada@example.com"' in after
    assert await tab.eval("document.title") == "Host"


async def test_oopif_box_is_in_top_level_coordinates(browser, local_server):
    tab = browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    box = await content_box(await tab.ref(_ref_of(text, '- button "Sign in"')))
    assert box["x"] == pytest.approx(_WIDGET_ORIGIN[0] + 10, abs=1)
    assert box["y"] == pytest.approx(_WIDGET_ORIGIN[1] + 10, abs=1)
    assert (box["width"], box["height"]) == pytest.approx((120, 40), abs=1)


async def test_human_click_in_an_oopif_hits_the_target_never_the_host(any_browser, local_server):
    tab = any_browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    signin = await tab.ref(_ref_of(text, '- button "Sign in"'))
    await signin.hover()
    await signin.click(human=True)
    assert '"signed in as"' in await tab.snapshot()
    assert await tab.eval("document.title") == "Host"  # "Delete account" untouched


async def test_covered_oopif_target_is_not_hittable(browser, local_server):
    tab = browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    signin = await tab.ref(_ref_of(text, '- button "Sign in"'))
    await tab.eval(
        "const c = document.createElement('div'); c.id = 'cover';"
        " c.style.cssText = 'position:fixed;inset:0;z-index:9';"
        " document.body.appendChild(c); true"
    )
    with pytest.raises(ElementNotHittableError, match="cover"):
        await signin.click(human=True)
    with pytest.raises(ElementNotHittableError):
        await signin.hover()
    assert '"signed out"' in await tab.snapshot()
    assert await tab.eval("document.title") == "Host"


@pytest.mark.parametrize("query", ["?zoom=1.5", "?zoom=0.8&nested"])
async def test_human_input_in_a_zoomed_oopif_reaches_its_target(browser, local_server, query):
    """The widget's own coordinates are scaled by the zoom: an unscaled click meant
    for Email lands on "Forget me"."""
    tab = browser.main_tab
    await _open(tab, local_server, query)
    text = await _snapshot_with(tab, '- button "Forget me"')
    email = await tab.ref(_ref_of(text, '- textbox "Email"'))
    zoom = float(query.split("=")[1].split("&")[0])
    box = await content_box(await tab.ref(_ref_of(text, '- button "Sign in"')))
    assert box["x"] == pytest.approx((_WIDGET_ORIGIN[0] + 10) * zoom, abs=2)
    assert box["width"] == pytest.approx(120 * zoom, abs=2)
    await email.click(human=True)
    await email.type("ada@example.com")
    await (await tab.ref(_ref_of(text, '- button "Sign in"'))).click(human=True)
    after = await tab.snapshot()
    assert '"signed in as ada@example.com"' in after, after
    if "nested" in query:
        deep = await tab.ref(_ref_of(text, '- button "Go deep"'))
        await deep.click(human=True)
        await _snapshot_with(tab, '- button "Gone deep"')
    assert await tab.eval("document.title") == "Host"


@pytest.mark.parametrize("query", ["?low", "?low&zoom=1.5"])
async def test_human_clicks_below_the_fold(browser, local_server, query):
    """Chrome hit-tests in document coordinates: the check must follow the scroll,
    in the host and in the widget alike."""
    tab = browser.main_tab
    await _open(tab, local_server, query)
    text = await _snapshot_with(tab, "Sign in")
    await (await tab.ref(_ref_of(text, '- button "Sign in"'))).click(human=True)
    assert '"signed in as"' in await tab.snapshot()
    assert await tab.eval("document.title") == "Host"
    await (await tab.ref(_ref_of(text, '- button "Cancel"'))).click(human=True)
    assert await tab.eval("document.title") == "cancelled"


async def test_oopif_inside_an_oopif(any_browser, local_server):
    tab = any_browser.main_tab
    await _open(tab, local_server, "?nested")
    text = await _snapshot_with(tab, '- button "Go deep"')
    assert "[oopif]" not in text
    assert len(await _iframe_targets(tab)) == 2  # the deep frame is a target of its own
    deep = await tab.ref(_ref_of(text, '- button "Go deep"'))
    box = await content_box(deep)
    assert box["x"] == pytest.approx(_WIDGET_ORIGIN[0] + 240 + 20, abs=1)
    assert box["y"] == pytest.approx(_WIDGET_ORIGIN[1] + 10 + 20, abs=1)
    await deep.click(human=True)
    await _snapshot_with(tab, '- button "Gone deep"')
    assert await tab.eval("document.title") == "Host"


async def test_oopif_refs_go_stale(browser, local_server):
    tab = browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    ref = _ref_of(text, '- button "Sign in"')
    await tab.eval("document.getElementById('login').remove(); true")
    with pytest.raises(StaleElementError, match="new snapshot"):
        await (await tab.ref(ref)).click()
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    ref = _ref_of(text, '- button "Sign in"')
    await tab.get(f"{local_server}/basic.html")
    with pytest.raises(StaleElementError):
        await tab.ref(ref)


async def test_placeholder_stays_when_the_oopif_cannot_be_reached(
    browser, local_server, monkeypatch
):
    from tellurium.browser import snapshot
    from tellurium.cdp.types import CDPError

    async def unreachable(*args, **kwargs):
        raise CDPError("No target with given id found", -32602)

    tab = browser.main_tab
    await _open(tab, local_server)
    await _snapshot_with(tab, "Sign in")
    monkeypatch.setattr(snapshot, "_oopif_session", unreachable)
    port = local_server.rsplit(":", 1)[1]
    text = await tab.snapshot()
    assert f'- iframe "http://localhost:{port}/oopif_login.html" [oopif]' in text


async def test_oopif_session_attached_by_hand_is_reused_and_detached(browser, local_server):
    """The router knows the target of every session: the snapshot reuses one already
    attached, and a session attached through the page detaches cleanly."""
    tab = browser.main_tab
    await _open(tab, local_server)
    await _snapshot_with(tab, "Sign in")
    router, port = tab._session.router, local_server.rsplit(":", 1)[1]
    targets = (await router.root.send("Target.getTargets", {}))["targetInfos"]
    (widget,) = [t for t in targets if t["url"].startswith(f"http://localhost:{port}")]
    used = router.session_for_target(widget["targetId"])
    assert used is not None and not used.closed
    await tab.snapshot()
    assert router.session_for_target(widget["targetId"]) is used  # no second attach
    extra = await router.attach(widget["targetId"], via=tab._session, timeout=5)
    assert extra is not used and router.session_for_target(widget["targetId"]) is used
    await router.detach(extra, via=tab._session)
    for _ in range(50):
        if extra.closed:
            break
        await asyncio.sleep(0.05)
    assert extra.closed and not used.closed


async def test_oopif_handle_is_released_in_the_oopif(browser, local_server):
    from tellurium.cdp.types import CDPError

    tab = browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    signin = await tab.ref(_ref_of(text, '- button "Sign in"'))
    session, object_id = signin._session, signin._object_id
    assert session is not tab._session
    await session.send("Runtime.getProperties", {"objectId": object_id})  # alive
    await signin.release()
    with pytest.raises(CDPError, match="Could not find object"):
        await session.send("Runtime.getProperties", {"objectId": object_id})


async def test_oopif_that_navigates_by_itself(browser, local_server):
    """The widget goes to its next step: its old refs are stale, its new ones work."""
    tab = browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Next step")
    old = _ref_of(text, '- button "Sign in"')
    await (await tab.ref(_ref_of(text, '- link "Next step"'))).click()
    text = await _snapshot_with(tab, '- button "Continue"')
    assert "Sign in" not in text
    with pytest.raises(StaleElementError):
        await (await tab.ref(old)).click()
    await (await tab.ref(_ref_of(text, '- button "Continue"'))).click(human=True)
    await _snapshot_with(tab, '- button "Continued"')
    assert await tab.eval("document.title") == "Host"


async def test_human_click_in_a_scrolled_oopif_in_a_scrolled_page(browser, local_server):
    tab = browser.main_tab
    await _open(tab, local_server, "?low&tall")
    text = await _snapshot_with(tab, '- button "Far away"')
    far = await tab.ref(_ref_of(text, '- button "Far away"'))
    await far.click(human=True)
    assert '"far"' in await tab.snapshot()
    widget_scroll = await far._call(
        "function() { return this.ownerDocument.scrollingElement.scrollTop; }"
    )
    assert widget_scroll > 0 and await tab.eval("scrollY") > 0
    assert await tab.eval("document.title") == "Host"
