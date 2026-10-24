"""A1 part A — accessibility snapshot and refs against a real Chrome (local fixtures)."""

from __future__ import annotations

import pytest

from tellurium.browser.snapshot import AXTree, fetch_tree

RESOLVER_FLAG = "--host-resolver-rules=MAP *.test 127.0.0.1"


def _roles_and_names(tree: AXTree) -> set[tuple[str, str]]:
    return {
        ((n.get("role") or {}).get("value", ""), (n.get("name") or {}).get("value", ""))
        for n in tree.nodes
    }


@pytest.fixture
async def isolating_browser():
    """A browser that resolves *.test to localhost, so a.test / b.test are two sites."""
    from tellurium import Browser

    b = await Browser.launch(headless=True, args=[RESOLVER_FLAG])
    yield b
    await b.close()


async def test_fetch_tree_stitches_a_same_process_iframe(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_iframe.html")
    tree = await fetch_tree(tab._session)
    assert ("button", "Top button") in _roles_and_names(tree)
    assert len(tree.frames) == 1
    (child,) = tree.frames.values()
    assert isinstance(child, AXTree)
    assert ("button", "Inner button") in _roles_and_names(child)


async def test_fetch_tree_marks_an_oopif_by_url(isolating_browser, local_server):
    port = local_server.rsplit(":", 1)[1]
    tab = isolating_browser.main_tab
    await tab.get(f"http://a.test:{port}/snapshot_oopif.html")
    tree = await fetch_tree(tab._session)
    assert list(tree.frames.values()) == [f"http://b.test:{port}/snapshot_child.html"]
