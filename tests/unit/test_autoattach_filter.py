"""Tests for Target.setAutoAttach filter (design doc 04 §P1.2)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from tellurium.browser.engine import StockEngine
from tellurium.stealth.engine import StealthEngine
from tellurium.stealth.profile import StealthProfile


def _make_engine() -> StealthEngine:
    """Construct a StealthEngine with a mock BrowserEngine, matching test_grease_brand.py pattern."""
    profile = StealthProfile.from_seed(seed=42)
    mock_engine = MagicMock(spec=StockEngine)
    mock_engine.capabilities.return_value = set()
    return StealthEngine(mock_engine, profile, headless=False, has_proxy=False)


def test_setup_auto_attach_sends_filter_for_stealth_targets():
    """Target.setAutoAttach payload must include a 'filter' list restricted
    to the target types the stealth engine actually patches."""
    engine = _make_engine()
    root_session = MagicMock()
    root_session.send = AsyncMock()

    asyncio.run(engine.setup_auto_attach(root_session))

    method, payload = root_session.send.call_args[0]
    assert method == "Target.setAutoAttach"
    assert payload["autoAttach"] is True
    assert payload["waitForDebuggerOnStart"] is False
    assert payload["flatten"] is True

    filt = payload.get("filter")
    assert isinstance(filt, list), "filter must be a list of TargetFilterEntry"
    filter_types = {entry["type"] for entry in filt}
    assert filter_types == {"iframe", "worker", "service_worker", "shared_worker"}, (
        f"Expected only stealth-relevant target types, got: {filter_types}"
    )


def test_setup_auto_attach_filter_excludes_page_and_browser():
    """'page' and 'browser' must NOT be in the filter (would cause double
    injection on main frame and deadlock on browser-level target)."""
    engine = _make_engine()
    root_session = MagicMock()
    root_session.send = AsyncMock()

    asyncio.run(engine.setup_auto_attach(root_session))

    _, payload = root_session.send.call_args[0]
    filter_types = {e["type"] for e in payload["filter"]}
    assert "page" not in filter_types
    assert "browser" not in filter_types
    assert "other" not in filter_types
