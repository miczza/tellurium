"""T7 parity test: tellurium-stock (stealth=True) closes the architectural gap
vs nodriver on the comparative detection suite.

**Scope:** Verify the 6 architectural checks pass. The 2 CreepJS checks
(`headless_pct`, `stealth_pct`) depend on the *quality* of the existing
stealth scripts (notably `webgl.js` platform-GPU coherence) and are tracked
as a follow-up; they are xfail-style here, visible in the report but not
blocking.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

STOCK_CHROME = os.environ.get("STOCK_CHROME", "/usr/bin/google-chrome-stable")
HERE = Path(__file__).parent


def _run_comparative(frameworks: str) -> dict:
    env = os.environ.copy()
    env["TELLURIUM_STEALTH_FLAG"] = "1"
    env.setdefault("DISPLAY", ":0")
    result = subprocess.run(
        [sys.executable, str(HERE / "comparative_test.py"),
         "--frameworks", frameworks,
         "--chrome-path", STOCK_CHROME],
        env=env, capture_output=True, text=True, timeout=600,
    )
    assert result.returncode == 0, f"comparative_test.py failed: {result.stderr[-2000:]}"
    return json.loads((HERE / "comparative_results.json").read_text())


# The 6 architectural checks T7 is responsible for closing.
ARCH_CHECKS = [
    ("webdriver_false", lambda r: r.get("webdriver_check", {}).get("webdriver") is False),
    ("sannysoft_0_failed", lambda r: r.get("sannysoft", {}).get("failed", 99) == 0),
    ("creepjs_lies_0", lambda r: r.get("creepjs", {}).get("lies_detected", -1) == 0),
    ("canvas_hash_present", lambda r: bool(r.get("browserleaks_canvas", {}).get("canvasHash"))),
    ("webgl_vendor_present", lambda r: bool(r.get("browserleaks_webgl", {}).get("vendor"))),
    ("browserscan_no_bot", lambda r: r.get("browserscan", {}).get("bot_detected") is False),
]

# The 2 CreepJS checks that remain sensitive to existing script quality
# (webgl.js GPU coherence, chrome_runtime.js, plugins.js). Tracked as
# follow-up T7.5; not blocking T7 merge.
CREEPJS_CHECKS = [
    ("creepjs_headless_0", lambda r: r.get("creepjs", {}).get("headless_pct", -1) == 0),
    ("creepjs_stealth_0", lambda r: r.get("creepjs", {}).get("stealth_pct", -1) == 0),
]


@pytest.mark.skipif(
    not os.path.exists(STOCK_CHROME),
    reason="Stock Chrome not installed",
)
def test_tellurium_passes_arch_checks_with_stealth():
    """T7 gate: all 6 architectural checks MUST pass on stock Chrome."""
    data = _run_comparative("tellurium")
    tel = data["tellurium"]

    failures = [name for (name, check) in ARCH_CHECKS if not check(tel)]
    assert not failures, (
        f"Architectural regressions: {failures}. "
        f"Details: {tel}"
    )


@pytest.mark.skipif(
    not os.path.exists(STOCK_CHROME),
    reason="Stock Chrome not installed",
)
def test_tellurium_matches_nodriver_on_creepjs():
    """T7.5 gate: CreepJS headless_pct and stealth_pct must both be 0.
    Fixed in T7.5 P3 by switching to a proper accessor getter that throws
    TypeError on non-instance 'this' (matching native getter behaviour) and
    using a split marker for cross-realm FPT identification."""
    data = _run_comparative("tellurium")
    tel = data["tellurium"]
    failures = [name for (name, check) in CREEPJS_CHECKS if not check(tel)]
    assert not failures, f"CreepJS signal leakage: {failures}. Details: creepjs={tel.get('creepjs')}"


@pytest.mark.skipif(
    not os.path.exists(STOCK_CHROME),
    reason="Stock Chrome not installed",
)
def test_tellurium_score_improved_vs_pre_t7():
    """Sanity: T7 moved tellurium from 5/8 to >=6/8."""
    data = _run_comparative("tellurium")
    tel = data["tellurium"]
    passed = sum(1 for (_, check) in (ARCH_CHECKS + CREEPJS_CHECKS) if check(tel))
    assert passed >= 6, (
        f"T7 score regressed below the 6/8 floor (got {passed}/8). "
        f"Details: {tel}"
    )
