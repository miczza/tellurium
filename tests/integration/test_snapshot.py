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
from tellurium.browser.snapshot import (
    AXTree,
    SnapshotTooLargeError,
    fetch_tree,
    take_snapshot,
    take_snapshot_nodes,
)

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


async def test_fetch_tree_reads_an_oopif_through_its_session(isolating_browser, local_server):
    port = local_server.rsplit(":", 1)[1]
    tab = isolating_browser.main_tab
    await tab.get(f"http://a.test:{port}/snapshot_oopif.html")
    tree = await fetch_tree(tab._session)
    (child,) = tree.frames.values()
    assert isinstance(child, AXTree) and child.owner and child.session is not tab._session
    assert ("button", "Inner button") in _roles_and_names(child)


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
    assert re.search(r'- textbox "Email" \[ref=e\d+\]: "ada@example.com"', text)
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
    inner_ref = _ref_of(text, '- button "Inner button"')
    inner = await resolve_ref(tab._session, tab, refs, inner_ref)
    assert await inner.attr("id") == "inner"
    # each ref knows its frame: the detached check runs in that frame's isolated world
    top_frame = refs.frame_of(_ref_of(text, '- button "Top button"'))
    assert top_frame == tab._frame_id
    assert refs.frame_of(inner_ref) not in ("", top_frame)


async def test_oopif_content_is_stitched(isolating_browser, local_server):
    """A2: the cross-site frame is read through its own session (more in
    test_snapshot_oopif.py); the [oopif] line is left for frames out of reach."""
    port = local_server.rsplit(":", 1)[1]
    tab = isolating_browser.main_tab
    await tab.get(f"http://a.test:{port}/snapshot_oopif.html")
    text = await take_snapshot(tab._session, RefMap())
    assert "[oopif]" not in text
    assert '- button "Inner button" [ref=' in text


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
    for _ in range(5):
        start = time.perf_counter()
        text = await take_snapshot(tab._session, refs)
        runs.append((time.perf_counter() - start) * 1000)
    # the best of five: a busy machine only ever adds time, never takes it away
    best = min(runs)
    METRICS.mkdir(parents=True, exist_ok=True)
    (METRICS / "A1-snapshot.json").write_text(
        json.dumps(
            {
                "name": "snapshot 5000-node page",
                "dom_nodes": dom_nodes,
                "elements": elements,
                "lines": text.count("\n") + 1,
                "runs_ms": [round(r, 1) for r in runs],
                "min_ms": round(best, 1),
                "median_ms": round(statistics.median(runs), 1),
                "limit_ms": 300,
            }
        )
    )
    assert best < 300, f"snapshot best {best:.0f} ms over {runs}"


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


async def test_selector_on_a_huge_page_fetches_only_the_subtree(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_huge.html")
    refs = _watched(tab)
    start = time.perf_counter()
    text = await take_snapshot(tab._session, refs, selector="#top")
    elapsed = time.perf_counter() - start
    assert text.splitlines()[0].startswith("- navigation [ref=")
    assert 'link "Help"' in text
    assert elapsed < 1.0, f"selector snapshot took {elapsed:.2f} s"


async def test_whole_huge_page_is_refused_fast_with_a_clear_error(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_huge.html")
    start = time.perf_counter()
    with pytest.raises(SnapshotTooLargeError, match="selector="):
        await take_snapshot(tab._session, RefMap())
    assert time.perf_counter() - start < 1.0


@pytest.mark.parametrize("selector", ["head", "#hidden"])
async def test_selector_on_a_node_without_ax_is_a_lookup_error(browser, local_server, selector):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_rerender.html")
    with pytest.raises(LookupError, match="accessibility"):
        await take_snapshot(tab._session, RefMap(), selector=selector)


async def test_human_actions_on_a_node_in_a_stitched_iframe_hit_that_node(browser, local_server):
    """Coordinates of an iframe's node are page coordinates, not the frame's: the
    click must not land on "Delete account" fixed at (0, 0) of the page."""
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_frame_danger.html")
    text = await take_snapshot(tab._session, refs)
    save = await resolve_ref(tab._session, tab, refs, _ref_of(text, '- button "Save"'))
    await save.hover()
    assert await (await tab.select("#hover")).text() == "save"
    await save.click(human=True)
    assert await (await tab.select("#status")).text() == "saved"


async def test_detached_check_does_not_trust_page_js(browser, local_server):
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_tamper.html")
    save = _ref_of(await take_snapshot(tab._session, refs), '- button "Save"')
    await tab.eval("lie(); rerender()")
    assert await tab.eval("document.createElement('b').isConnected") is True  # the lie works
    with pytest.raises(StaleElementError):
        await resolve_ref(tab._session, tab, refs, save)
    assert await (await tab.select("#status")).text() == "idle"


async def test_rerender_while_the_pointer_travels_sends_no_click(browser, local_server):
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_tamper.html")
    save = await resolve_ref(
        tab._session, tab, refs, _ref_of(await take_snapshot(tab._session, refs), '- button "Save"')
    )
    await tab.eval("rerenderOnScroll()")
    with pytest.raises(StaleElementError):
        await save.click(human=True)
    assert await (await tab.select("#status")).text() == "idle"


async def test_detached_garbage_does_not_count_toward_the_limit(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    await tab.eval("window.junk = Array.from({length: 70000}, () => document.createElement('div'))")
    text = await take_snapshot(tab._session, RefMap())
    assert '- button "Sign in" [ref=' in text


async def test_max_nodes_lifts_the_limit_and_the_error_says_how(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_huge.html")
    with pytest.raises(SnapshotTooLargeError, match=r"60\d\d\d DOM nodes.*max_nodes="):
        await take_snapshot(tab._session, RefMap())
    limits = {"max_nodes": 100_000, "snapshot_timeout": 30}
    text = await take_snapshot(tab._session, RefMap(), **limits, max_chars=500)
    assert '- button "Row 0" [ref=' in text


@pytest.mark.parametrize("selector", ["body", "html"])
async def test_body_and_html_selectors_give_the_whole_page(browser, local_server, selector):
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_form.html")
    whole = await take_snapshot(tab._session, refs)
    assert await take_snapshot(tab._session, refs, selector=selector) == whole


async def test_selector_on_a_huge_subtree_is_refused_with_a_clear_error(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_huge.html")
    start = time.perf_counter()
    with pytest.raises(SnapshotTooLargeError, match="selector="):
        await take_snapshot(tab._session, RefMap(), selector="#rows")
    assert time.perf_counter() - start < 12


@pytest.mark.parametrize("mode", ["frame", "ancestor", "cover"])
async def test_human_click_never_lands_on_another_element(browser, local_server, mode):
    """Zoomed frames skew Chrome's quads; an overlay hides the target: either the
    click reaches Save, or nothing is sent and the error says what is on top."""
    from tellurium.browser.geometry import ElementNotHittableError

    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_zoom.html?{mode}")
    text = await take_snapshot(tab._session, refs)
    save = await resolve_ref(tab._session, tab, refs, _ref_of(text, '- button "Save"'))
    status = await tab.select("#status")
    for _ in range(3):
        try:
            await save.click(human=True)
        except ElementNotHittableError as exc:
            assert "on top" in str(exc)
            if mode == "cover":
                assert "cover" in str(exc)
        assert await status.text() in ("idle", "saved"), mode
    if mode == "cover":
        assert await status.text() == "idle"
        with pytest.raises(ElementNotHittableError):
            await save.hover()


async def test_tree_too_slow_to_fetch_is_refused_in_time(browser, local_server):
    """Shadow DOM escapes the node count: the fetch has its own time limit."""
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_shadow.html")
    for selector in (None, "#host"):  # the count is low: a selector fetches it all too
        start = time.perf_counter()
        with pytest.raises(SnapshotTooLargeError) as raised:
            await take_snapshot(tab._session, RefMap(), selector=selector, snapshot_timeout=0.5)
        # Bounded near the limit (the unguarded fetch took ~9 s); slack for a loaded machine.
        assert time.perf_counter() - start < 3.0
        message = str(raised.value)
        assert "snapshot_timeout=0.5" in message and "shadow DOM" in message
        assert "selector=" not in message  # it would not help here
    # The tab is still usable afterwards. Not timed: on this page a selector still
    # fetches the whole 120k-node AX tree (shadow DOM, see backlog), ~4-5 s on master.
    assert await tab.eval("document.title") is not None
    text = await take_snapshot(tab._session, RefMap(), selector="h1", snapshot_timeout=60)
    assert text.startswith('- heading "Web component"')


async def test_human_click_goes_through_what_a_person_clicks_through(browser, local_server):
    """A pointer-events:none overlay does not stop a real click, nor does a custom
    checkbox whose transparent input sits under its own <label for>."""
    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_hit.html")
    text = await take_snapshot(tab._session, refs)
    under_glass = await resolve_ref(
        tab._session, tab, refs, _ref_of(text, '- button "Under glass"')
    )
    await under_glass.click(human=True)
    assert await (await tab.select("#status")).text() == "c4"
    switch = await resolve_ref(tab._session, tab, refs, _ref_of(text, '- checkbox "Dark mode"'))
    await switch.hover()
    await switch.click(human=True)
    assert await switch.is_checked()


@pytest.mark.parametrize("mode", ["frame", "ancestor"])
async def test_drag_from_a_zoomed_frame_sends_no_press_elsewhere(browser, local_server, mode):
    from tellurium.browser.geometry import ElementNotHittableError

    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_zoom.html?{mode}")
    text = await take_snapshot(tab._session, refs)
    save = await resolve_ref(tab._session, tab, refs, _ref_of(text, '- button "Save"'))
    with pytest.raises(ElementNotHittableError):
        await save.drag_to(await tab.select("#status"))
    assert await (await tab.select("#status")).text() == "idle"


@pytest.mark.parametrize(("name", "other"), [("Accept", "link"), ("Notify", "#od")])
async def test_a_control_inside_the_label_is_not_the_target(browser, local_server, name, other):
    """A hit in the target's label counts only if no other control lies on the way."""
    from tellurium.browser.geometry import ElementNotHittableError

    tab = browser.main_tab
    refs = _watched(tab)
    await tab.get(f"{local_server}/snapshot_hit.html")
    text = await take_snapshot(tab._session, refs)
    target = await resolve_ref(tab._session, tab, refs, _ref_of(text, f'- checkbox "{name}"'))
    with pytest.raises(ElementNotHittableError):
        await target.click(human=True)
    assert not await target.is_checked()
    assert await (await tab.select("#status")).text() == "idle"
    assert not await (await tab.select("#od")).is_checked()
