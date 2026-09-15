"""Stealth profile UA / Client Hints follow the version of the launched binary."""

from tellurium.stealth._grease import parse_product_version
from tellurium.stealth.profile import StealthProfile


def test_parse_product_version():
    assert parse_product_version("Chrome/153.0.8010.36") == "153.0.8010.36"
    assert parse_product_version("HeadlessChrome/152.0.7977.120") == "152.0.7977.120"
    assert parse_product_version("") is None
    assert parse_product_version("Chrome") is None
    assert parse_product_version("Chrome/153.0") is None


def test_with_browser_version_rewrites_ua_and_client_hints():
    p = StealthProfile.from_seed(7)
    q = p.with_browser_version("153.0.8010.36")
    assert q.browser_version == "153.0.8010.36"
    assert "Chrome/153.0.8010.36" in q.user_agent
    assert 'v="153"' in q.ch_ua
    assert "153.0.8010.36" in q.ch_ua_full_version_list
    # everything else untouched
    assert (q.seed, q.target_os, q.screen_width, q.hardware_concurrency, q.languages) == (
        p.seed,
        p.target_os,
        p.screen_width,
        p.hardware_concurrency,
        p.languages,
    )
    assert p.browser_version != q.browser_version  # original not mutated
