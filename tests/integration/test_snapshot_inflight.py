"""P3 part B — snapshots of one document share the AX tree request in flight."""

from __future__ import annotations

import asyncio

import pytest

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


@pytest.mark.parametrize("touch", ["eval", "keys"])
async def test_input_after_the_request_starts_a_new_one(browser, local_server, monkeypatch, touch):
    """What the tab sends after a tree was asked for may change the page: the tree in
    flight is not handed to a later snapshot, which asks for its own."""
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_shadow.html")
    sent = _count_full_trees(monkeypatch, tab._session)
    with pytest.raises(SnapshotTooLargeError):
        await take_snapshot(tab._session, RefMap(), snapshot_timeout=0.3)
    if touch == "eval":
        await tab.eval("document.querySelector('h1').textContent = 'Changed'")
        expected = '- heading "Changed"'
    else:
        await tab.eval(
            "document.addEventListener('keydown', () => {"
            " document.querySelector('h1').textContent = 'Pressed' }); 1"
        )
        await tab.keyboard_press("Enter")
        expected = '- heading "Pressed"'
    text = await take_snapshot(tab._session, RefMap(), selector="h1", snapshot_timeout=60)
    assert text.startswith(expected), text
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
