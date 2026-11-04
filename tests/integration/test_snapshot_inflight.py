"""P3 part B — snapshots of one document share the AX tree request in flight."""

from __future__ import annotations

import asyncio

import pytest

from tellurium.browser import snapshot
from tellurium.browser.refs import RefMap
from tellurium.browser.snapshot import SnapshotTooLargeError, take_snapshot


def _count_full_trees(monkeypatch, session) -> list[str]:
    """The ``getFullAXTree`` commands sent on *session* from now on."""
    sent: list[str] = []
    send = session.send

    async def counting(method, params=None, timeout=None):
        if method == "Accessibility.getFullAXTree":
            sent.append(method)
        return await send(method, params, timeout)

    monkeypatch.setattr(session, "send", counting)
    return sent


async def test_concurrent_selector_snapshots_send_one_full_tree(browser, local_server, monkeypatch):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_shadow.html")
    sent = _count_full_trees(monkeypatch, tab._session)
    texts = await asyncio.gather(
        *(
            take_snapshot(tab._session, RefMap(), selector=selector, snapshot_timeout=60)
            for selector in ("h1", "#host", "body")
        )
    )
    assert texts[0].startswith('- heading "Web component"')
    assert "Shadow 39999" in texts[1] and "Shadow 39999" in texts[2]
    assert len(sent) == 1


async def test_a_snapshot_after_an_abandoned_one_joins_its_request(
    browser, local_server, monkeypatch
):
    """A snapshot past its snapshot_timeout leaves Chrome building the tree: the next
    one on the same document waits for that tree instead of queueing another."""
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_shadow.html")
    sent = _count_full_trees(monkeypatch, tab._session)
    with pytest.raises(SnapshotTooLargeError):
        await take_snapshot(tab._session, RefMap(), snapshot_timeout=0.3)
    text = await take_snapshot(tab._session, RefMap(), selector="h1", snapshot_timeout=60)
    assert text.startswith('- heading "Web component"')
    assert len(sent) == 1


async def test_input_sent_while_the_tree_is_in_flight_starts_a_new_request(
    browser, local_server, monkeypatch
):
    """An eval sent while a tree is being built, and still unanswered (the renderer
    is busy with that tree), may change the page: a snapshot taken meanwhile does not
    get the tree in flight, it asks for its own, which comes after the eval."""
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_shadow.html")
    sent = _count_full_trees(monkeypatch, tab._session)
    with pytest.raises(SnapshotTooLargeError):
        await take_snapshot(tab._session, RefMap(), snapshot_timeout=0.3)
    change = asyncio.ensure_future(tab.eval("document.querySelector('h1').textContent = 'Changed'"))
    await asyncio.sleep(0)  # sent: its answer waits for the tree
    taking = asyncio.ensure_future(
        take_snapshot(tab._session, RefMap(), selector="h1", snapshot_timeout=60)
    )
    await asyncio.sleep(0.05)
    assert not change.done()  # the input is concurrent with the tree in flight
    text = await taking
    await change
    assert text.startswith('- heading "Changed"'), text
    assert len(sent) == 2


async def _frame_session(tab):
    """The session of the cross-site iframe of the page, its document loaded."""
    router = tab._session.router
    for _ in range(100):
        targets = (await router.root.send("Target.getTargets", {}))["targetInfos"]
        frames = [t for t in targets if t["type"] == "iframe" and "snapshot_child" in t["url"]]
        if frames:
            target = frames[0]["targetId"]
            child = router.session_for_target(target)
            child = child or await router.attach(target, via=tab._session, timeout=5)
            ready = await child.send("Runtime.evaluate", {"expression": "document.readyState"})
            if ready["result"]["value"] == "complete":
                return child
        await asyncio.sleep(0.05)
    raise AssertionError("the cross-site iframe never loaded")


async def test_input_unanswered_when_the_tree_is_asked_for_is_not_shared(
    browser, local_server, monkeypatch
):
    """An input sent just before a tree is asked for, answered while the tree is
    built: what it does may reach the page after the tree (a cross-site iframe that
    posts to its parent goes through the browser). A snapshot after the input gets a
    tree of its own, not the one in flight."""
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_shadow_oopif.html")
    child = await _frame_session(tab)
    document = (await tab._session.send("DOM.getDocument", {"depth": 0}))["root"]["backendNodeId"]
    sent = _count_full_trees(monkeypatch, tab._session)
    script = {"expression": "parent.postMessage('after', '*'); 1"}
    posted = asyncio.ensure_future(child.send("Runtime.evaluate", script, timeout=10))
    await asyncio.sleep(0)  # sent, not answered yet
    tree = asyncio.ensure_future(snapshot._full_tree(tab._session, None, document, 60, {}))
    await posted
    assert not tree.done()  # the input answered while the tree is in flight
    text = await take_snapshot(tab._session, RefMap(), selector="h1", snapshot_timeout=60)
    await tree
    assert text.startswith('- heading "After"'), text
    assert len(sent) == 2


async def test_a_new_document_starts_a_new_request(browser, local_server, monkeypatch):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_shadow.html")
    sent = _count_full_trees(monkeypatch, tab._session)
    with pytest.raises(SnapshotTooLargeError):
        await take_snapshot(tab._session, RefMap(), snapshot_timeout=0.3)
    await tab.get(f"{local_server}/snapshot_form.html")
    text = await take_snapshot(tab._session, RefMap(), snapshot_timeout=60)
    assert '- button "Sign in"' in text
    assert len(sent) == 2


async def _closed_session(browser):
    """The session of a tab opened and closed: its commands raise, allocating no id."""
    gone = await browser.new_tab()
    session = gone._session
    await gone.close()
    for _ in range(100):
        if session.closed:
            return session
        await asyncio.sleep(0.05)
    raise AssertionError("the closed tab's session is still open")


async def test_snapshots_failing_on_a_closed_session_do_not_hide_an_input(
    browser, local_server, monkeypatch
):
    """A snapshot of a tab already gone sends nothing: inputs sent while the tree is
    in flight, as many commands as it tried, still make that tree stale."""
    tab = browser.main_tab
    gone = await _closed_session(browser)
    await tab.get(f"{local_server}/snapshot_shadow.html")
    sent = _count_full_trees(monkeypatch, tab._session)
    with pytest.raises(SnapshotTooLargeError):
        await take_snapshot(tab._session, RefMap(), snapshot_timeout=0.3)
    router, change = tab._session.router, "document.querySelector('h1').textContent = 'Changed'"
    before = router._next_msg_id
    inputs = asyncio.gather(tab.eval(change), tab.eval(change))  # answered after the tree
    while router._next_msg_id - before < 2:
        await asyncio.sleep(0.01)
    with pytest.raises(ConnectionError):  # tries DOM.getDocument, then Accessibility.disable
        await take_snapshot(gone, RefMap(), snapshot_timeout=5)
    assert not inputs.done()  # the tree asked for before them is still being built
    text = await take_snapshot(tab._session, RefMap(), selector="h1", snapshot_timeout=60)
    await inputs
    assert text.startswith('- heading "Changed"'), text
    assert len(sent) == 2
