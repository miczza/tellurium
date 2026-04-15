"""Tests for GREASE brand extraction from Browser.getVersion output."""
import pytest
from tellurium.stealth._grease import parse_grease_brands


def test_parse_grease_brands_extracts_not_a_brand_entry():
    """Given a brands list with one GREASE entry, return its brand+version."""
    brands = [
        {"brand": "Chromium", "version": "146"},
        {"brand": "Google Chrome", "version": "146"},
        {"brand": "Not?A_Brand", "version": "8"},
    ]
    brand, version = parse_grease_brands(brands)
    assert brand == "Not?A_Brand"
    assert version == "8"


def test_parse_grease_brands_handles_randomized_token():
    """GREASE token can be any of several forms (Not;A=Brand, Not?A_Brand, ...).
    Helper must detect it by pattern, not exact match."""
    brands = [
        {"brand": "Chromium", "version": "147"},
        {"brand": "Not;A=Brand", "version": "99"},
        {"brand": "Google Chrome", "version": "147"},
    ]
    brand, version = parse_grease_brands(brands)
    assert brand == "Not;A=Brand"
    assert version == "99"


def test_parse_grease_brands_fallback_when_no_grease_entry():
    """If no GREASE-like entry is present, return the known fallback
    ('Not_A Brand', '24') — matches pre-review 2026-04-15 hardcoded value."""
    brands = [
        {"brand": "Chromium", "version": "146"},
        {"brand": "Google Chrome", "version": "146"},
    ]
    brand, version = parse_grease_brands(brands)
    assert brand == "Not_A Brand"
    assert version == "24"


import asyncio
from unittest.mock import AsyncMock, MagicMock
from tellurium.stealth.engine import StealthEngine
from tellurium.stealth.profile import StealthProfile


def test_engine_uses_profile_grease_brand(monkeypatch):
    """When profile.grease_brand is set, engine must not emit 'Not_A Brand'."""
    import dataclasses
    profile = StealthProfile.from_seed(seed=42)
    profile = dataclasses.replace(profile, grease_brand="Not?A_Brand", grease_version="8")

    from tellurium.browser.engine import StockEngine
    mock_engine = MagicMock(spec=StockEngine)
    mock_engine.capabilities.return_value = set()

    engine = StealthEngine(mock_engine, profile, headless=False, has_proxy=False)
    session = MagicMock()
    session.send = AsyncMock()

    asyncio.run(engine._set_ua_override(session))

    # Inspect the CDP payload
    _, payload = session.send.call_args[0]
    brands = payload["userAgentMetadata"]["brands"]
    assert {"brand": "Not?A_Brand", "version": "8"} in brands
    assert not any(b["brand"] == "Not_A Brand" for b in brands), (
        "Hardcoded fallback must not be present when profile has real GREASE"
    )
