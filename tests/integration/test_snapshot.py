"""A1 part A — accessibility snapshot and refs against a real Chrome (local fixtures)."""

from __future__ import annotations

import json
import re
import statistics
import time
from pathlib import Path

import pytest

from tellurium.browser.handles import StaleElementError
from tellurium.browser.refs import RefMap, resolve_ref
from tellurium.browser.snapshot import AXTree, fetch_tree, take_snapshot, take_snapshot_nodes

# The gate reads metrics the tests leave here (build/ is not versioned).
METRICS = Path(__file__).parents[2] / "build" / "metrics"

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


def _ref_of(text: str, line_start: str) -> str:
    """The ref on the first line of *text* that starts (after indent) with *line_start*."""
    for line in text.splitlines():
        if line.strip().startswith(line_start):
            match = re.search(r"\[ref=(e\d+)\]", line)
            assert match, line
            return match.group(1)
    raise AssertionError(f"no line starting with {line_start!r} in:\n{text}")


def _watched(tab) -> RefMap:
    """A RefMap reset on main-frame navigation, as the tab will hold it (part B)."""
    refs = RefMap()
    tab._session.on("Page.frameNavigated", refs.on_frame_navigated)
    return refs


async def test_snapshot_of_a_login_form(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    text = await take_snapshot(tab._session, _watched(tab))
    assert '- heading "Sign in" [level=1] [ref=' in text
    assert re.search(r'- textbox "Email" \[ref=e\d+\]: ada@example.com', text)
    assert re.search(r'- checkbox "Remember me" \[checked\] \[ref=e\d+\]', text)
    assert re.search(r'- button "Single sign-on" \[disabled\] \[ref=e\d+\]', text)


async def test_refs_act_on_the_right_elements(browser, local_server):
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/login.html")
    text = await take_snapshot(tab._session, refs, interactive=True)
    user, password = re.findall(r"- textbox \[ref=(e\d+)\]", text)
    for ref, value in ((user, "ada"), ("@" + password, "secret")):
        element = await resolve_ref(tab._session, tab, refs, ref)
        await element.type(value)
    button = await resolve_ref(tab._session, tab, refs, _ref_of(text, '- button "Sign in"'))
    await button.click(human=True)
    status = await tab.select("#status")
    assert await status.text() == "logged in as ada"


async def test_same_node_same_ref_until_navigation(browser, local_server):
    tab = browser.main_tab
    refs = _watched(tab)
    url = f"{local_server}/snapshot_form.html"
    await tab.get(url)
    first = await take_snapshot(tab._session, refs)
    second = await take_snapshot(tab._session, refs, interactive=True)
    ref = _ref_of(first, '- textbox "Email"')
    assert _ref_of(second, '- textbox "Email"') == ref
    element = await resolve_ref(tab._session, tab, refs, ref)
    assert await element.attr("id") == "email"

    await tab.get(url)  # same page, new document: the old ref must not resolve
    with pytest.raises(StaleElementError):
        await resolve_ref(tab._session, tab, refs, ref)
    fresh = await take_snapshot(tab._session, refs)
    assert _ref_of(fresh, '- textbox "Email"') != ref
    with pytest.raises(LookupError):
        await resolve_ref(tab._session, tab, refs, "e99999")


async def test_selector_scopes_the_snapshot(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    text = await take_snapshot(tab._session, _watched(tab), selector="#login")
    assert text.startswith("- form [ref=")
    assert "navigation" not in text
    with pytest.raises(LookupError):
        await take_snapshot(tab._session, RefMap(), selector="#nope")


async def test_depth_and_max_chars(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_list.html")
    refs = _watched(tab)
    shallow = await take_snapshot(tab._session, refs, depth=1)
    assert shallow.splitlines() == [
        f'- heading "Items" [level=1] [ref={_ref_of(shallow, "- heading")}]',
        f"- list [ref={_ref_of(shallow, '- list')}]",
    ]
    cut = await take_snapshot(tab._session, refs, max_chars=2000)
    assert len(cut) <= 2000
    assert re.search(r"truncated: \d+ more lines", cut.splitlines()[-1])


async def test_snapshot_nodes_are_structured(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    nodes = await take_snapshot_nodes(tab._session, _watched(tab), interactive=True)
    email = next(n for n in nodes if n.name == "Email")
    assert (email.role, email.value) == ("textbox", "ada@example.com")
    assert email.ref and email.ref.startswith("e")


async def test_same_process_iframe_content_is_in_the_snapshot(browser, local_server):
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_iframe.html")
    text = await take_snapshot(tab._session, refs)
    assert '- iframe "Child frame" [ref=' in text
    inner = await resolve_ref(tab._session, tab, refs, _ref_of(text, '- button "Inner button"'))
    assert await inner.attr("id") == "inner"


async def test_oopif_shows_as_a_placeholder(isolating_browser, local_server):
    port = local_server.rsplit(":", 1)[1]
    tab = isolating_browser.main_tab
    await tab.get(f"http://a.test:{port}/snapshot_oopif.html")
    text = await take_snapshot(tab._session, RefMap())
    assert f'- iframe "http://b.test:{port}/snapshot_child.html" [oopif]' in text


async def test_snapshot_works_with_stealth(stealth_browser, local_server):
    tab = stealth_browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    text = await take_snapshot(tab._session, RefMap(), interactive=True)
    assert '- button "Sign in" [ref=' in text


_COUNT_NODES = """(() => {
  const walker = document.createTreeWalker(document, NodeFilter.SHOW_ALL);
  let n = 1;
  while (walker.nextNode()) n++;
  return n;
})()"""


async def test_five_thousand_node_page_snapshot_time(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_list.html")
    elements = await tab.eval("document.getElementsByTagName('*').length")
    dom_nodes = await tab.eval(_COUNT_NODES)
    assert dom_nodes >= 5000
    refs = _watched(tab)
    await take_snapshot(tab._session, refs)  # warm-up: Chrome builds its AX tree once
    runs = []
    for _ in range(3):
        start = time.perf_counter()
        text = await take_snapshot(tab._session, refs)
        runs.append((time.perf_counter() - start) * 1000)
    median = statistics.median(runs)
    METRICS.mkdir(parents=True, exist_ok=True)
    (METRICS / "A1-snapshot.json").write_text(
        json.dumps(
            {
                "name": "snapshot 5000-node page",
                "dom_nodes": dom_nodes,
                "elements": elements,
                "lines": text.count("\n") + 1,
                "runs_ms": [round(r, 1) for r in runs],
                "median_ms": round(median, 1),
                "limit_ms": 300,
            }
        )
    )
    assert median < 300, f"snapshot median {median:.0f} ms over {runs}"


async def test_ref_of_a_rerendered_node_is_stale_not_another_element(browser, local_server):
    """A node detached by an SPA re-render must never act: no click lands on
    whatever sits at (0, 0) of an empty box."""
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_rerender.html")
    text = await take_snapshot(tab._session, refs)
    save = _ref_of(text, '- button "Save"')
    await tab.eval("rerender()")
    for _ in range(4):
        with pytest.raises(StaleElementError):
            element = await resolve_ref(tab._session, tab, refs, save)
            await element.click(human=True)
    status = await tab.select("#status")
    assert await status.text() == "idle"
    # a new snapshot gives the new node its own ref, and that one works
    fresh = await take_snapshot(tab._session, refs)
    new_save = _ref_of(fresh, '- button "Save"')
    assert new_save != save
    await (await resolve_ref(tab._session, tab, refs, new_save)).click(human=True)
    assert await status.text() == "saved"


async def test_ref_after_document_open_is_stale(browser, local_server):
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_form.html")
    ref = _ref_of(await take_snapshot(tab._session, refs), '- button "Sign in"')
    await tab.eval("document.open(); document.write('<button>Sign in</button>'); document.close()")
    with pytest.raises(StaleElementError):
        await resolve_ref(tab._session, tab, refs, ref)
