"""Unit tests for the per-tab ref map (``tellurium.browser.refs``)."""

from __future__ import annotations

import pytest

from tellurium.browser.handles import StaleElementError
from tellurium.browser.refs import RefMap, parse_ref


def test_parse_ref_accepts_bare_and_at_forms():
    assert parse_ref("e3") == "e3"
    assert parse_ref("@e3") == "e3"
    assert parse_ref("  @e12 ") == "e12"


@pytest.mark.parametrize("text", ["#e3", "e", "@e", "e3x", "button", "e-1", "", "@@e3", "e03"])
def test_parse_ref_rejects_everything_else(text):
    assert parse_ref(text) is None


def test_same_node_keeps_its_ref():
    refs = RefMap()
    first = refs.ref_for(101)
    second = refs.ref_for(202)
    assert first != second
    assert refs.ref_for(101) == first
    assert refs.lookup(first) == 101
    assert refs.lookup("@" + second) == 202


def test_refs_start_at_e1():
    assert RefMap().ref_for(7) == "e1"


def test_unknown_ref_is_a_lookup_error():
    refs = RefMap()
    refs.ref_for(1)
    with pytest.raises(LookupError):
        refs.lookup("e99")
    with pytest.raises(LookupError):
        refs.lookup("not-a-ref")


def test_refs_of_a_previous_document_are_stale_and_never_reused():
    refs = RefMap()
    old = refs.ref_for(5)
    generation = refs.generation
    refs.reset()
    assert refs.generation == generation + 1
    with pytest.raises(StaleElementError):
        refs.lookup(old)
    # The same backend id in the new document gets a fresh ref: an old ref
    # can never point at a node of another document.
    new = refs.ref_for(5)
    assert new != old
    assert refs.lookup(new) == 5
    with pytest.raises(StaleElementError):
        refs.lookup(old)


def test_stale_is_not_a_lookup_error():
    # Callers tell the two apart: a gone node vs a ref that never existed.
    assert not issubclass(StaleElementError, LookupError)


def test_main_frame_navigation_resets_child_frame_does_not():
    refs = RefMap()
    ref = refs.ref_for(9)
    refs.on_frame_navigated({"frame": {"id": "child", "parentId": "main"}})
    assert refs.lookup(ref) == 9
    refs.on_frame_navigated({"frame": {"id": "main"}})
    with pytest.raises(StaleElementError):
        refs.lookup(ref)


def test_resolution_without_navigation_keeps_generation():
    refs = RefMap()
    refs.ref_for(1)
    generation = refs.generation
    refs.ref_for(2)
    assert refs.generation == generation


class _FakeSession:
    """Answers DOM.resolveNode; optionally runs *during* before answering."""

    def __init__(self, during=None, connected=True):
        self.calls: list[tuple[str, dict]] = []
        self._during = during
        self._connected = connected

    async def send(self, method, params=None, timeout=None):
        self.calls.append((method, params))
        if method == "Runtime.callFunctionOn":
            return {"result": {"type": "boolean", "value": self._connected}}
        if self._during:
            self._during()
        return {"object": {"objectId": "obj-1"}}


class _FakeTab:
    pass


async def test_resolve_ref_builds_an_element_from_the_backend_id():
    from tellurium.browser.refs import resolve_ref

    refs = RefMap()
    ref = refs.ref_for(42)
    session = _FakeSession()
    element = await resolve_ref(session, _FakeTab(), refs, "@" + ref)
    assert session.calls[0] == ("DOM.resolveNode", {"backendNodeId": 42})
    assert session.calls[1][0] == "Runtime.callFunctionOn"
    assert element._object_id == "obj-1"


async def test_resolve_ref_uses_the_tab_handle_group():
    from tellurium.browser.handles import HandleGroup
    from tellurium.browser.refs import resolve_ref

    refs = RefMap()
    ref = refs.ref_for(42)
    session = _FakeSession()
    tab = _FakeTab()
    tab._handles = HandleGroup(session)
    await resolve_ref(session, tab, refs, ref)
    assert session.calls[0][1]["objectGroup"] == tab._handles.name


async def test_navigation_during_resolution_is_stale():
    from tellurium.browser.refs import resolve_ref

    refs = RefMap()
    ref = refs.ref_for(42)
    session = _FakeSession(during=refs.reset)
    with pytest.raises(StaleElementError):
        await resolve_ref(session, _FakeTab(), refs, ref)


async def test_resolve_unknown_ref_sends_nothing():
    from tellurium.browser.refs import resolve_ref

    session = _FakeSession()
    with pytest.raises(LookupError):
        await resolve_ref(session, _FakeTab(), RefMap(), "e5")
    assert session.calls == []


async def test_detached_node_is_stale_and_its_handle_released():
    from tellurium.browser.handles import HandleGroup
    from tellurium.browser.refs import resolve_ref

    refs = RefMap()
    ref = refs.ref_for(42)
    session = _FakeSession(connected=False)
    tab = _FakeTab()
    tab._handles = HandleGroup(session)
    with pytest.raises(StaleElementError, match="no longer in the page"):
        await resolve_ref(session, tab, refs, ref)
    await tab._handles.drain()
    assert ("Runtime.releaseObject", {"objectId": "obj-1"}) in session.calls


def test_refs_remember_their_frame_until_reset():
    refs = RefMap()
    ref = refs.ref_for(7, "frame-A")
    assert refs.ref_for(7) == ref and refs.frame_of(ref) == "frame-A"
    assert refs.frame_of("e999") == "" and refs.frame_of("junk") == ""
    refs.reset()
    assert refs.frame_of(ref) == ""


def test_same_backend_id_in_another_renderer_gets_its_own_ref():
    refs = RefMap()
    top = refs.ref_for(7, "main")
    inner = refs.ref_for(7, "oopif", "S1")
    assert inner != top
    assert refs.ref_for(7, "oopif", "S1") == inner and refs.ref_for(7) == top
    assert refs.lookup(inner) == 7 and refs.frame_of(inner) == "oopif"


def test_refs_remember_the_session_of_their_document_until_reset():
    refs, oopif = RefMap(), object()
    refs.bind("S1", oopif)
    inner, top = refs.ref_for(3, "f", "S1"), refs.ref_for(3, "main")
    assert refs.session_of(inner) is oopif
    assert refs.session_of(top) is None and refs.session_of("e999") is None
    refs.reset()
    assert refs.session_of(inner) is None


def test_settle_keeps_the_owner_of_pending_refs():
    from tellurium.browser.refs import pending_ref
    from tellurium.browser.snapshot import SnapshotNode

    refs = RefMap()
    nodes = [SnapshotNode(pending_ref(5, "main"), "button", "a")]
    nodes[0].children = [SnapshotNode(pending_ref(5, "inner", "S1"), "button", "b")]
    refs.settle(nodes)
    assert nodes[0].ref == "e1" and nodes[0].children[0].ref == "e2"
    assert refs.frame_of("e2") == "inner" and refs.ref_for(5, "x", "S1") == "e2"


async def test_resolve_ref_asks_the_session_of_the_ref_document():
    from tellurium.browser.refs import resolve_ref

    refs, tab_session, oopif = RefMap(), _FakeSession(), _FakeSession()
    refs.bind("S1", oopif)
    element = await resolve_ref(tab_session, _FakeTab(), refs, refs.ref_for(42, "f", "S1"))
    assert tab_session.calls == []
    assert oopif.calls[0] == ("DOM.resolveNode", {"backendNodeId": 42})
    assert element._session is oopif


async def test_ref_in_a_frame_whose_session_is_gone_is_stale():
    from tellurium.browser.refs import resolve_ref

    class _Gone:
        async def send(self, method, params=None, timeout=None):
            raise ConnectionError("Target detached (session S1)")

    refs = RefMap()
    refs.bind("S1", _Gone())
    with pytest.raises(StaleElementError, match="take a new snapshot"):
        await resolve_ref(_FakeSession(), _FakeTab(), refs, refs.ref_for(42, "f", "S1"))


def test_another_document_of_an_owner_turns_its_refs_stale():
    refs, oopif = RefMap(), object()
    refs.bind("S1", oopif, "L1")
    old, top = refs.ref_for(3, "f", "S1"), refs.ref_for(3, "main")
    assert refs.document_of(old) == ("S1", "L1")
    refs.bind("S1", oopif, "L1")  # same document: nothing changes
    assert refs.lookup(old) == 3
    refs.bind("S1", oopif, "L2")  # the frame loaded another document
    with pytest.raises(StaleElementError):
        refs.lookup(old)
    new = refs.ref_for(3, "f", "S1")
    assert new != old and refs.document_of(new) == ("S1", "L2")
    assert refs.lookup(top) == 3 and refs.document_of(top) == ("", "")
