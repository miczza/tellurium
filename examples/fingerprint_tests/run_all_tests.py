#!/usr/bin/env python3
"""
Complete fingerprint test suite for chromium-telluride C2.

Runs:
1. Quick fingerprint collection (local)
2. Stability verification (same seed = same result)
3. Variation verification (different seed = different result)
4. Live site tests (FingerprintJS, CreepJS, BrowserLeaks)

Usage:
    python run_all_tests.py [--quick-only] [--chrome PATH]
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from test_fingerprint_sites import run_tests as run_site_tests
from test_fingerprint_sites import validate_results

from tellurium import Browser

CHROMIUM_TELLURIDE_PATH = "/home/miczza/PycharmProjects/chromium-telluride/src/out/Release/chrome"
SEED_A = 42069
SEED_B = 99999


FINGERPRINT_JS = """
(async () => {
    const result = {};

    // Simple hash function (djb2) - doesn't require secure context
    function simpleHash(str) {
        let hash = 5381;
        for (let i = 0; i < str.length; i++) {
            hash = ((hash << 5) + hash) + str.charCodeAt(i);
            hash = hash & hash; // Convert to 32bit integer
        }
        return (hash >>> 0).toString(16).padStart(8, '0');
    }

    // Canvas
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 50;
    const ctx = canvas.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillStyle = '#f60';
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = '#069';
    ctx.fillText('Cwm fjord bank glyphs vext quiz', 2, 15);
    ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
    ctx.fillText('Cwm fjord bank glyphs vext quiz', 4, 17);
    const dataUrl = canvas.toDataURL();
    result.canvas_hash = simpleHash(dataUrl);
    result.canvas_length = dataUrl.length;

    // Audio
    try {
        const actx = new OfflineAudioContext(1, 44100, 44100);
        const osc = actx.createOscillator();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(10000, actx.currentTime);
        const comp = actx.createDynamicsCompressor();
        comp.threshold.setValueAtTime(-50, actx.currentTime);
        comp.knee.setValueAtTime(40, actx.currentTime);
        comp.ratio.setValueAtTime(12, actx.currentTime);
        comp.attack.setValueAtTime(0, actx.currentTime);
        comp.release.setValueAtTime(0.25, actx.currentTime);
        osc.connect(comp);
        comp.connect(actx.destination);
        osc.start(0);
        const buffer = await actx.startRendering();
        const data = buffer.getChannelData(0);
        let sum = 0;
        for (let i = 4500; i < 5000; i++) sum += Math.abs(data[i]);
        result.audio = sum.toFixed(8);
    } catch (e) {
        result.audio = 'error: ' + e.message;
    }

    // Text metrics
    const tctx = document.createElement('canvas').getContext('2d');
    tctx.font = '16px Arial';
    const m = tctx.measureText('Cwm fjord bank glyphs vext quiz');
    result.text_width = m.width;

    // Client rects
    const div = document.createElement('div');
    div.style.cssText = 'position:absolute;left:100px;top:100px;width:200px;height:50px;';
    div.textContent = 'Test';
    document.body.appendChild(div);
    const rect = div.getBoundingClientRect();
    document.body.removeChild(div);
    result.rect_width = rect.width;

    // WebGPU
    if (navigator.gpu) {
        try {
            const adapter = await navigator.gpu.requestAdapter();
            if (adapter) {
                const info = await adapter.requestAdapterInfo();
                result.webgpu = {
                    vendor: info.vendor,
                    architecture: info.architecture,
                    device: info.device
                };
            }
        } catch (e) {
            result.webgpu = { error: e.message };
        }
    }

    return result;
})()
"""


TEST_PAGE = "data:text/html,<!DOCTYPE html><html><head></head><body></body></html>"


async def collect_fingerprint(seed: int, chrome_path: str) -> dict:
    """Collect fingerprint for a seed."""
    browser = await Browser.launch(
        headless=False,
        executable=chrome_path,
        args=[
            f"--fingerprint={seed}",
            "--fingerprint-platform=linux",
            "--no-sandbox",
            "--window-size=1920,1080",
        ],
    )
    try:
        tab = await browser.new_tab()
        await tab.get(TEST_PAGE)
        await asyncio.sleep(1)
        result = await tab.eval(FINGERPRINT_JS)
        if result is None:
            result = {"error": "eval returned None"}
        return result
    finally:
        await browser.close()


async def test_stability(chrome_path: str) -> dict:
    """Test that same seed produces same fingerprint."""
    print("\n[1/3] STABILITY TEST")
    print("=" * 50)
    print(f"Running seed {SEED_A} twice...")

    fp1 = await collect_fingerprint(SEED_A, chrome_path)
    fp2 = await collect_fingerprint(SEED_A, chrome_path)

    result = {"test": "stability", "seed": SEED_A, "pass": True, "details": {}}

    checks = ["canvas_hash", "audio", "text_width", "rect_width"]
    for key in checks:
        v1, v2 = fp1.get(key), fp2.get(key)
        match = v1 == v2
        result["details"][key] = {
            "run1": str(v1)[:32] if isinstance(v1, str) and len(str(v1)) > 32 else v1,
            "run2": str(v2)[:32] if isinstance(v2, str) and len(str(v2)) > 32 else v2,
            "match": match,
        }
        if not match:
            result["pass"] = False
        status = "PASS" if match else "FAIL"
        print(f"  {key}: {status}")

    overall = "PASS" if result["pass"] else "FAIL"
    print(f"\nStability: {overall}")
    return result


async def test_variation(chrome_path: str) -> dict:
    """Test that different seeds produce different fingerprints."""
    print("\n[2/3] VARIATION TEST")
    print("=" * 50)
    print(f"Comparing seed {SEED_A} vs {SEED_B}...")

    fp1 = await collect_fingerprint(SEED_A, chrome_path)
    fp2 = await collect_fingerprint(SEED_B, chrome_path)

    result = {"test": "variation", "seed1": SEED_A, "seed2": SEED_B, "pass": True, "details": {}}

    checks = ["canvas_hash", "audio", "text_width"]
    for key in checks:
        v1, v2 = fp1.get(key), fp2.get(key)
        differs = v1 != v2
        result["details"][key] = {
            "seed1": str(v1)[:32] if isinstance(v1, str) and len(str(v1)) > 32 else v1,
            "seed2": str(v2)[:32] if isinstance(v2, str) and len(str(v2)) > 32 else v2,
            "differs": differs,
        }
        if not differs:
            result["pass"] = False
        status = "PASS" if differs else "FAIL"
        print(f"  {key}: {status} ({'differs' if differs else 'same'})")

    overall = "PASS" if result["pass"] else "FAIL"
    print(f"\nVariation: {overall}")
    return result


async def test_live_sites(chrome_path: str) -> dict:
    """Test against real fingerprinting sites."""
    print("\n[3/3] LIVE SITE TESTS")
    print("=" * 50)

    results = await run_site_tests(SEED_A, chrome_path)
    critical, warnings = validate_results(results)

    result = {
        "test": "live_sites",
        "seed": SEED_A,
        "pass": len(critical) == 0,
        "critical_failures": critical,
        "warnings": warnings,
        "sites": results,
    }

    if critical:
        print("\n  CRITICAL FAILURES:")
        for c in critical:
            print(f"    FAIL: {c}")
    if warnings:
        print("\n  WARNINGS:")
        for w in warnings:
            print(f"    WARN: {w}")
    if not critical:
        print("\n  All site checks PASSED")

    return result


async def main():
    parser = argparse.ArgumentParser(description="Complete fingerprint test suite")
    parser.add_argument("--quick-only", action="store_true", help="Skip live site tests")
    parser.add_argument("--chrome", type=str, default=CHROMIUM_TELLURIDE_PATH, help="Chrome path")
    args = parser.parse_args()

    print("=" * 60)
    print("CHROMIUM-TELLURIDE FINGERPRINT TEST SUITE")
    print("=" * 60)
    print(f"Chrome: {args.chrome}")
    print(f"Seeds: {SEED_A}, {SEED_B}")
    print(f"Started: {datetime.now().isoformat()}")

    results = {"timestamp": datetime.now().isoformat(), "chrome_path": args.chrome, "tests": []}

    # Run tests
    stability = await test_stability(args.chrome)
    results["tests"].append(stability)

    variation = await test_variation(args.chrome)
    results["tests"].append(variation)

    if not args.quick_only:
        live = await test_live_sites(args.chrome)
        results["tests"].append(live)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_pass = all(t.get("pass", True) for t in results["tests"])

    print(f"Stability: {'PASS' if stability['pass'] else 'FAIL'}")
    print(f"Variation: {'PASS' if variation['pass'] else 'FAIL'}")

    if not args.quick_only:
        # FingerprintJS results
        fpjs = live["sites"].get("fingerprintjs", {})
        if fpjs.get("visitor_id"):
            print(f"FingerprintJS ID: {fpjs['visitor_id']}")
        if fpjs.get("confidence"):
            conf_status = "PASS" if fpjs["confidence"] >= 0.5 else "WARN"
            print(f"FingerprintJS Confidence: {fpjs['confidence']} ({conf_status})")

        # CreepJS results
        creepjs = live["sites"].get("creepjs", {})
        trust = creepjs.get("trust_score")
        lies = creepjs.get("lies_detected")
        headless = creepjs.get("headless_score")

        if trust is not None:
            trust_status = "PASS" if trust >= 70 else "WARN" if trust >= 50 else "FAIL"
            print(f"CreepJS Trust: {trust}% ({trust_status})")
        if headless is not None:
            headless_status = "PASS" if headless <= 20 else "WARN" if headless <= 50 else "FAIL"
            print(f"CreepJS Headless: {headless}% ({headless_status})")
        if lies is not None:
            lies_status = "PASS" if lies <= 2 else "WARN" if lies <= 5 else "FAIL"
            print(f"CreepJS Lies: {lies} ({lies_status})")

    overall = "PASS" if all_pass else "FAIL"
    print(f"\nOverall: {overall}")

    # Save report
    output_file = Path(__file__).parent / "test_report.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull report: {output_file}")
    print(f"Screenshots: {Path(__file__).parent / 'screenshots'}")


if __name__ == "__main__":
    asyncio.run(main())
