#!/usr/bin/env python3
"""
Quick fingerprint verification for chromium-telluride.

Collects fingerprint data directly from the browser without external sites.
Faster and more reliable for development testing.

Usage:
    python quick_fingerprint_test.py [--seed SEED] [--compare SEED2]
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tellurium import Browser

CHROMIUM_TELLURIDE_PATH = "/home/miczza/PycharmProjects/chromium-telluride/src/out/Release/chrome"


TEST_PAGE = "data:text/html,<!DOCTYPE html><html><head></head><body></body></html>"


FINGERPRINT_JS = """
(async () => {
    const result = {};

    // Simple hash function (djb2) - doesn't require secure context
    function simpleHash(str) {
        let hash = 5381;
        for (let i = 0; i < str.length; i++) {
            hash = ((hash << 5) + hash) + str.charCodeAt(i);
            hash = hash & hash;
        }
        return (hash >>> 0).toString(16).padStart(8, '0');
    }

    // Canvas fingerprint
    try {
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
        result.canvas = {
            hash: simpleHash(dataUrl),
            length: dataUrl.length
        };
    } catch (e) {
        result.canvas = { error: e.message };
    }

    // Audio fingerprint
    try {
        const ctx = new OfflineAudioContext(1, 44100, 44100);
        const oscillator = ctx.createOscillator();
        oscillator.type = 'triangle';
        oscillator.frequency.setValueAtTime(10000, ctx.currentTime);
        const compressor = ctx.createDynamicsCompressor();
        compressor.threshold.setValueAtTime(-50, ctx.currentTime);
        compressor.knee.setValueAtTime(40, ctx.currentTime);
        compressor.ratio.setValueAtTime(12, ctx.currentTime);
        compressor.attack.setValueAtTime(0, ctx.currentTime);
        compressor.release.setValueAtTime(0.25, ctx.currentTime);
        oscillator.connect(compressor);
        compressor.connect(ctx.destination);
        oscillator.start(0);
        const buffer = await ctx.startRendering();
        const data = buffer.getChannelData(0);
        let sum = 0;
        for (let i = 4500; i < 5000; i++) sum += Math.abs(data[i]);
        result.audio = {
            fingerprint: sum.toFixed(8),
            sample: Array.from(data.slice(4500, 4510))
        };
    } catch (e) {
        result.audio = { error: e.message };
    }

    // Text metrics
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        ctx.font = '16px Arial';
        const metrics = ctx.measureText('Cwm fjord bank glyphs vext quiz');
        result.textMetrics = {
            width: metrics.width,
            actualBoundingBoxLeft: metrics.actualBoundingBoxLeft,
            actualBoundingBoxRight: metrics.actualBoundingBoxRight,
            fontBoundingBoxAscent: metrics.fontBoundingBoxAscent,
            fontBoundingBoxDescent: metrics.fontBoundingBoxDescent
        };
    } catch (e) {
        result.textMetrics = { error: e.message };
    }

    // Client rects
    try {
        const div = document.createElement('div');
        div.style.cssText = 'position:absolute;left:100px;top:100px;width:200px;height:50px;';
        div.textContent = 'Test element';
        document.body.appendChild(div);
        const rect = div.getBoundingClientRect();
        document.body.removeChild(div);
        result.clientRects = {
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height
        };
    } catch (e) {
        result.clientRects = { error: e.message };
    }

    // WebGPU
    try {
        if (!navigator.gpu) {
            result.webgpu = { available: false };
        } else {
            const adapter = await navigator.gpu.requestAdapter();
            if (!adapter) {
                result.webgpu = { available: true, adapter: null };
            } else {
                const info = await adapter.requestAdapterInfo();
                result.webgpu = {
                    available: true,
                    vendor: info.vendor,
                    architecture: info.architecture,
                    device: info.device,
                    description: info.description
                };
            }
        }
    } catch (e) {
        result.webgpu = { error: e.message };
    }

    // Client hints
    try {
        if (navigator.userAgentData) {
            const high = await navigator.userAgentData.getHighEntropyValues([
                'platform', 'platformVersion', 'architecture', 'bitness'
            ]);
            result.clientHints = {
                brands: navigator.userAgentData.brands,
                mobile: navigator.userAgentData.mobile,
                platform: high.platform,
                platformVersion: high.platformVersion,
                architecture: high.architecture,
                bitness: high.bitness
            };
        } else {
            result.clientHints = null;
        }
    } catch (e) {
        result.clientHints = { error: e.message };
    }

    // Navigator basics
    result.navigator = {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        language: navigator.language,
        hardwareConcurrency: navigator.hardwareConcurrency,
        deviceMemory: navigator.deviceMemory
    };

    return result;
})()
"""


async def collect_fingerprint(seed: int, chrome_path: str) -> dict:
    """Collect fingerprint data with a specific seed."""
    print(f"Collecting fingerprint with seed={seed}...")

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

        data = await tab.eval(FINGERPRINT_JS)
        data["seed"] = seed
        data["timestamp"] = datetime.now().isoformat()

        return data
    finally:
        await browser.close()


def compare_fingerprints(fp1: dict, fp2: dict) -> dict:
    """Compare two fingerprints and report differences."""
    report = {
        "seed1": fp1["seed"],
        "seed2": fp2["seed"],
        "differences": {},
        "pass": True,
    }

    # Canvas should differ
    c1 = fp1.get("canvas", {}).get("hash")
    c2 = fp2.get("canvas", {}).get("hash")
    if c1 and c2:
        differs = c1 != c2
        report["differences"]["canvas_hash"] = {
            "seed1": c1[:16] + "...",
            "seed2": c2[:16] + "...",
            "differs": differs,
            "expected": True,
            "status": "PASS" if differs else "FAIL",
        }
        if not differs:
            report["pass"] = False

    # Audio should differ
    a1 = fp1.get("audio", {}).get("fingerprint")
    a2 = fp2.get("audio", {}).get("fingerprint")
    if a1 and a2:
        differs = a1 != a2
        report["differences"]["audio"] = {
            "seed1": a1,
            "seed2": a2,
            "differs": differs,
            "expected": True,
            "status": "PASS" if differs else "FAIL",
        }
        if not differs:
            report["pass"] = False

    # Text metrics should differ slightly
    t1 = fp1.get("textMetrics", {}).get("width")
    t2 = fp2.get("textMetrics", {}).get("width")
    if t1 and t2:
        differs = abs(t1 - t2) > 0.0001
        report["differences"]["textMetrics_width"] = {
            "seed1": t1,
            "seed2": t2,
            "differs": differs,
            "expected": True,
            "status": "PASS" if differs else "FAIL",
        }
        if not differs:
            report["pass"] = False

    # Client rects should differ slightly
    r1 = fp1.get("clientRects", {}).get("width")
    r2 = fp2.get("clientRects", {}).get("width")
    if r1 and r2:
        differs = abs(r1 - r2) > 0.0001
        report["differences"]["clientRects_width"] = {
            "seed1": r1,
            "seed2": r2,
            "differs": differs,
            "expected": True,
            "status": "PASS" if differs else "FAIL",
        }

    return report


def check_stability(fp1: dict, fp2: dict) -> dict:
    """Check that same seed produces identical results."""
    report = {"seed": fp1["seed"], "stable": True, "differences": []}

    # Canvas should be identical
    c1 = fp1.get("canvas", {}).get("hash")
    c2 = fp2.get("canvas", {}).get("hash")
    if c1 != c2:
        report["stable"] = False
        report["differences"].append(f"canvas_hash: {c1} vs {c2}")

    # Audio should be identical
    a1 = fp1.get("audio", {}).get("fingerprint")
    a2 = fp2.get("audio", {}).get("fingerprint")
    if a1 != a2:
        report["stable"] = False
        report["differences"].append(f"audio: {a1} vs {a2}")

    # Text metrics should be identical
    t1 = fp1.get("textMetrics", {}).get("width")
    t2 = fp2.get("textMetrics", {}).get("width")
    if t1 != t2:
        report["stable"] = False
        report["differences"].append(f"textMetrics_width: {t1} vs {t2}")

    return report


async def main():
    parser = argparse.ArgumentParser(description="Quick fingerprint test for chromium-telluride")
    parser.add_argument("--seed", type=int, default=42069, help="Primary seed")
    parser.add_argument("--compare", type=int, help="Second seed for comparison")
    parser.add_argument("--chrome", type=str, default=CHROMIUM_TELLURIDE_PATH, help="Chrome path")
    parser.add_argument("--stability", action="store_true", help="Run stability check")
    args = parser.parse_args()

    output_dir = Path(__file__).parent

    # Collect primary fingerprint
    fp1 = await collect_fingerprint(args.seed, args.chrome)
    with open(output_dir / f"fingerprint_{args.seed}.json", "w") as f:
        json.dump(fp1, f, indent=2)
    print(f"\nFingerprint saved to fingerprint_{args.seed}.json")

    print("\n" + "=" * 50)
    print(f"FINGERPRINT SUMMARY (seed={args.seed})")
    print("=" * 50)
    print(f"Canvas Hash: {fp1.get('canvas', {}).get('hash', 'N/A')[:32]}...")
    print(f"Audio: {fp1.get('audio', {}).get('fingerprint', 'N/A')}")
    print(f"Text Width: {fp1.get('textMetrics', {}).get('width', 'N/A')}")
    print(f"Client Rect Width: {fp1.get('clientRects', {}).get('width', 'N/A')}")
    print(f"WebGPU: {fp1.get('webgpu', {})}")

    # Comparison test
    if args.compare:
        print(f"\nCollecting comparison fingerprint (seed={args.compare})...")
        fp2 = await collect_fingerprint(args.compare, args.chrome)
        with open(output_dir / f"fingerprint_{args.compare}.json", "w") as f:
            json.dump(fp2, f, indent=2)

        report = compare_fingerprints(fp1, fp2)
        print("\n" + "=" * 50)
        print("COMPARISON REPORT")
        print("=" * 50)
        for key, diff in report["differences"].items():
            print(f"{key}: {diff['status']}")
            print(f"  Seed {fp1['seed']}: {diff['seed1']}")
            print(f"  Seed {fp2['seed']}: {diff['seed2']}")

        overall = "PASS" if report["pass"] else "FAIL"
        print(f"\nOverall: {overall}")

    # Stability test
    if args.stability:
        print(f"\nRunning stability check (seed={args.seed})...")
        fp2 = await collect_fingerprint(args.seed, args.chrome)

        stability = check_stability(fp1, fp2)
        print("\n" + "=" * 50)
        print("STABILITY REPORT")
        print("=" * 50)
        status = "PASS" if stability["stable"] else "FAIL"
        print(f"Stability: {status}")
        if stability["differences"]:
            print("Differences found:")
            for d in stability["differences"]:
                print(f"  - {d}")


if __name__ == "__main__":
    asyncio.run(main())
