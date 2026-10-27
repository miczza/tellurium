"""Where ``trap_link.reasons`` runs its check: the isolated world, retried once, never
the page's; one call, with nothing forced on the page."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tellurium.browser.element import Element
from tellurium.cdp.types import CDPError
from tellurium.stealth import trap_link


class _Session:
    def __init__(self, *, stale_worlds=0, worlds=True):
        self.calls: list[tuple[str, dict]] = []
        self._stale, self._worlds, self._next = stale_worlds, worlds, 100

    async def send(self, method, params, timeout=None):
        self.calls.append((method, params))
        if method == "DOM.describeNode":
            return {"node": {"backendNodeId": 7}}
        if method == "Page.createIsolatedWorld":
            if not self._worlds:
                raise CDPError("No frame for given id found", -32000)
            self._next += 1
            return {"executionContextId": self._next}
        if method == "DOM.resolveNode":
            if self._stale:
                self._stale -= 1
                raise CDPError("Cannot find context with specified id", -32000)
            return {"object": {"objectId": f"iso-{params['executionContextId']}"}}
        if method == "Runtime.callFunctionOn":
            found = {"reasons": ["empty"], "nofollow": False, "framed": False}
            return {"result": {"type": "object", "value": found}}
        raise AssertionError(method)

    def target(self) -> str:
        return next(p["objectId"] for m, p in self.calls if m == "Runtime.callFunctionOn")


def _element(session: _Session, cached_world: int | None = None) -> Element:
    worlds = {} if cached_world is None else {"F": cached_world}
    tab = SimpleNamespace(_session=session, _frame_id="F", _hsim_worlds=worlds)
    return Element(session, tab, object_id="page-1")


async def test_the_check_runs_on_the_node_resolved_in_the_isolated_world():
    session = _Session()
    assert await trap_link.reasons(_element(session)) == ["empty"]
    assert session.target() == "iso-101"


async def test_a_world_of_a_gone_document_is_replaced_once():
    session = _Session(stale_worlds=1)
    element = _element(session, cached_world=99)
    assert await trap_link.is_trap_link(element) is True
    assert session.target() == "iso-101"
    assert element._tab._hsim_worlds == {"F": 101}


async def test_without_an_isolated_world_the_check_does_not_run():
    session = _Session(worlds=False)
    with pytest.raises(trap_link.NoIsolatedWorldError):
        await trap_link.reasons(_element(session))
    assert not [m for m, _ in session.calls if m == "Runtime.callFunctionOn"]


async def test_the_check_is_one_call_that_forces_nothing():
    """Focus rules are read in the isolated world, not applied: no ``CSS`` domain."""
    session = _Session()
    await trap_link.reasons(_element(session))
    methods = [m for m, _ in session.calls]
    assert methods.count("Runtime.callFunctionOn") == 1
    assert not [m for m in methods if m.startswith("CSS.")]


def test_the_check_is_the_script_shipped_with_the_stealth_scripts():
    from tellurium.stealth.extension import SCRIPTS_DIR

    script = (SCRIPTS_DIR / "trap_link.js").read_text()
    assert trap_link._REASONS_JS == script
