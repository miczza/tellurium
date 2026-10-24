"""Tab.snapshot / snapshot_nodes / ref / select("@eN") with a real Chrome (local fixtures)."""

from __future__ import annotations

import re

import pytest

from tellurium import Element, SnapshotNode, SnapshotTooLargeError, StaleElementError


def _ref_of(text: str, line_start: str) -> str:
    """The ref on the first line of *text* that starts (after indent) with *line_start*."""
    for line in text.splitlines():
        if line.strip().startswith(line_start):
            match = re.search(r"\[ref=(e\d+)\]", line)
            assert match, line
            return match.group(1)
    raise AssertionError(f"no line starting with {line_start!r} in:\n{text}")


def _walk(nodes: list[SnapshotNode]):
    for node in nodes:
        yield node
        yield from _walk(node.children)


async def test_login_form_through_refs(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/login.html")
    text = await tab.snapshot(interactive=True)
    user, password = re.findall(r"- textbox \[ref=(e\d+)\]", text)
    await (await tab.select("@" + user)).type("ada")
    field = await tab.ref(password)
    assert isinstance(field, Element)
    await field.type("secret")
    await (await tab.select("@" + _ref_of(text, '- button "Sign in"'))).click(human=True)
    assert await (await tab.select("#status")).text() == "logged in as ada"


async def test_snapshot_text_and_filters(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    text = await tab.snapshot()
    assert re.search(r'- textbox "Email" \[ref=e\d+\]: "ada@example.com"', text)
    assert re.search(r'- checkbox "Remember me" \[checked\] \[ref=e\d+\]', text)
    assert '- heading "Sign in"' in text
    interactive = await tab.snapshot(interactive=True)
    assert "heading" not in interactive and '- button "Sign in"' in interactive
    scoped = await tab.snapshot(selector="nav")
    assert '- link "Home"' in scoped and "Email" not in scoped
    shallow = await tab.snapshot(depth=0)
    assert all(not line.startswith(" ") for line in shallow.splitlines())
    cut = await tab.snapshot(max_chars=120)
    assert len(cut) <= 120 and "truncated" in cut


async def test_snapshot_nodes_share_refs_with_the_text(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    nodes = await tab.snapshot_nodes()
    email = next(n for n in _walk(nodes) if n.role == "textbox" and n.name == "Email")
    assert email.value == "ada@example.com"
    assert _ref_of(await tab.snapshot(), '- textbox "Email"') == email.ref
    assert await (await tab.ref(email.ref)).attr("id") == "email"


async def test_same_ref_within_a_document_stale_after_navigation(browser, local_server):
    tab = browser.main_tab
    url = f"{local_server}/snapshot_form.html"
    await tab.get(url)
    ref = _ref_of(await tab.snapshot(), '- textbox "Email"')
    assert _ref_of(await tab.snapshot(interactive=True), '- textbox "Email"') == ref
    await tab.get(url)  # same page, new document
    for call in (tab.ref(ref), tab.select(f"@{ref}")):
        with pytest.raises(StaleElementError):
            await call
    fresh = _ref_of(await tab.snapshot(), '- textbox "Email"')
    assert fresh != ref
    assert await (await tab.select(f"@{fresh}")).attr("id") == "email"


async def test_unknown_ref_is_a_lookup_error_without_waiting(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    with pytest.raises(LookupError):
        await tab.ref("e99999")
    with pytest.raises(LookupError):
        await tab.select("@e99999", timeout=30)  # a ref is never polled for


async def test_ref_of_a_rerendered_node_is_stale(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_rerender.html")
    save = _ref_of(await tab.snapshot(), '- button "Save"')
    await tab.eval("rerender()")
    with pytest.raises(StaleElementError):
        await (await tab.select(f"@{save}")).click(human=True)
    assert await (await tab.select("#status")).text() == "idle"


async def test_human_click_on_a_same_process_iframe_ref(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_frame_danger.html")
    text = await tab.snapshot()
    await (await tab.select("@" + _ref_of(text, '- button "Save"'))).click(human=True)
    assert await (await tab.select("#status")).text() == "saved"


async def test_long_list_snapshot_and_ref(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_list.html")
    text = await tab.snapshot(interactive=True)
    assert text.count("- button") == 1000
    button = await tab.ref(_ref_of(text, '- button "Open 999"'))
    assert await button.text() == "Open 999"


async def test_snapshot_limits_reach_the_tab(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_list.html")
    with pytest.raises(SnapshotTooLargeError, match="max_nodes=100"):
        await tab.snapshot(max_nodes=100)
    assert "- button" in await tab.snapshot(max_nodes=None, snapshot_timeout=10)


async def test_css_selectors_still_work(browser, local_server):
    tab = browser.main_tab
    await tab.get(f"{local_server}/snapshot_form.html")
    assert await (await tab.select("#email")).attr("id") == "email"
    with pytest.raises(TimeoutError):
        await tab.select("e3", timeout=0.3)  # without "@" it is a CSS type selector


async def test_refs_with_stealth(stealth_browser, local_server):
    tab = stealth_browser.main_tab
    await tab.get(f"{local_server}/login.html")
    text = await tab.snapshot(interactive=True)
    user = re.findall(r"- textbox \[ref=(e\d+)\]", text)[0]
    await (await tab.select(f"@{user}")).type("ada", human=True)
    assert await tab.eval("document.getElementById('user').value") == "ada"
