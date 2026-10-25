"""A2 part C — refs of a cross-site iframe (OOPIF) whose document changes process.

The widget goes from localhost to 127.0.0.2: another site, so Chrome swaps its
renderer while the frame, its target and our session stay. Backend ids start again
in the new renderer: an old ref must not land on the node that now has its id.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from tellurium.browser.handles import StaleElementError
from tests.integration.test_snapshot_oopif import _open, _ref_of, _snapshot_with


async def _widget(tab):
    router = tab._session.router
    targets = (await router.root.send("Target.getTargets", {}))["targetInfos"]
    (widget,) = [t for t in targets if t["type"] == "iframe"]
    return widget, router.session_for_target(widget["targetId"])


async def _move_widget(tab, other_server: str) -> None:
    """Send the widget to 127.0.0.2 and wait until its new document is loaded."""
    before, session = await _widget(tab)
    url = f"{other_server}/oopif_pay.html"
    await tab.eval(f"document.getElementById('login').src = {url!r}; true")
    for _ in range(100):
        widget, now = await _widget(tab)
        if widget["url"] == url:
            ready = await now.send("Runtime.evaluate", {"expression": "document.readyState"})
            if ready["result"]["value"] == "complete":
                break
        await asyncio.sleep(0.05)
    else:
        raise AssertionError("the widget never reached 127.0.0.2")
    # the premise: same frame, same session, another renderer
    assert widget["targetId"] == before["targetId"] and now is session


def _widget_refs(text: str) -> set[str]:
    """The refs of the lines nested under the iframe line (not the <iframe>'s own)."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('- iframe "Login"'))
    inside = []
    for line in lines[start + 1 :]:
        if not line.startswith("  "):
            break
        inside.append(line)
    return set(re.findall(r"\[ref=(e\d+)\]", "\n".join(inside)))


async def _state(tab) -> str:
    text = await tab.snapshot()
    match = re.search(r'paragraph \[ref=e\d+\]: "([^"]*)"', text.split("Pay 1")[0])
    return match.group(1) if match else text


async def test_old_ref_is_stale_after_the_oopif_changes_process(
    any_browser, local_server, other_server
):
    tab = any_browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    old = [_ref_of(text, f"- {line}") for line in ('button "Sign in"', 'textbox "Email"')]
    await _move_widget(tab, other_server)
    _, session = await _widget(tab)
    await session.send("DOM.getDocument", {"depth": -1})  # the new renderer hands out ids
    for ref in old:
        with pytest.raises(StaleElementError, match="new snapshot"):
            await (await tab.ref(ref)).click()
    assert await _state(tab) == "idle"
    assert await tab.eval("document.title") == "Host"


async def test_new_snapshot_never_reuses_a_ref_of_the_old_document(
    browser, local_server, other_server
):
    tab = browser.main_tab
    await _open(tab, local_server)
    text = await _snapshot_with(tab, "Sign in")
    old = _widget_refs(text)
    await _move_widget(tab, other_server)
    after = await _snapshot_with(tab, '- button "Pay 60"')
    new = _widget_refs(after)
    assert old and new and not old & new
    for ref in old:
        with pytest.raises(StaleElementError):
            await (await tab.ref(ref)).click()
    assert await _state(tab) == "idle"
    pay = await tab.ref(_ref_of(after, '- button "Pay 3"'))
    await pay.click()
    assert await _state(tab) == "hit x3"
