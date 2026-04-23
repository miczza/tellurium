#!/usr/bin/env python3
"""
Automated fingerprint testing for chromium-telluride.

Tests against:
- FingerprintJS demo
- CreepJS
- BrowserLeaks Canvas
- BrowserLeaks WebGL

Usage:
    python test_fingerprint_sites.py [--seed SEED] [--chrome PATH]
"""

import asyncio
import argparse
import json
import hashlib
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tellurium import Browser


CHROMIUM_TELLURIDE_PATH = "/home/miczza/PycharmProjects/chromium-telluride/src/out/Release/chrome"


async def test_fingerprintjs(tab, results: dict) -> None:
    """Test FingerprintJS demo site."""
    print("  Testing fingerprintjs.com...")
    await tab.get("https://fingerprintjs.github.io/fingerprintjs/", timeout=60)
    await asyncio.sleep(5)  # Wait for fingerprint to compute

    # Extract fingerprint data
    data = await tab.eval("""
    (async () => {
        // Wait for FingerprintJS to load
        await new Promise(r => setTimeout(r, 2000));

        const result = {};

        // Try to get visitor ID from page
        const visitorEl = document.querySelector('.visitor-id, [data-visitor-id], .fp-result');
        if (visitorEl) {
            result.visitorId = visitorEl.textContent.trim();
        }

        // Get all fingerprint components if available
        const components = document.querySelectorAll('.component, .fp-component, tr');
        result.components = {};
        components.forEach(c => {
            const name = c.querySelector('.name, td:first-child')?.textContent?.trim();
            const value = c.querySelector('.value, td:last-child')?.textContent?.trim();
            if (name && value) {
                result.components[name] = value;
            }
        });

        // Check for any warnings/errors
        result.warnings = [];
        document.querySelectorAll('.warning, .error, .alert').forEach(el => {
            result.warnings.push(el.textContent.trim());
        });

        return result;
    })()
    """)

    results["fingerprintjs"] = data
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "fingerprintjs.png"), full_page=True)
    print(f"    Visitor ID: {data.get('visitorId', 'N/A')}")
    print(f"    Warnings: {len(data.get('warnings', []))}")


async def test_creepjs(tab, results: dict) -> None:
    """Test CreepJS site."""
    print("  Testing creepjs.com...")
    await tab.get("https://abrahamjuliot.github.io/creepjs/", timeout=60)
    await asyncio.sleep(10)  # CreepJS needs more time

    data = await tab.eval("""
    (async () => {
        // Wait for analysis to complete
        await new Promise(r => setTimeout(r, 5000));

        const result = {
            trustScore: null,
            liesDetected: 0,
            fingerprint: null,
            details: {}
        };

        // Get trust score
        const trustEl = document.querySelector('.trust-score, [class*="trust"], .score');
        if (trustEl) {
            const match = trustEl.textContent.match(/(\\d+)/);
            if (match) result.trustScore = parseInt(match[1]);
        }

        // Count lies
        const liesEls = document.querySelectorAll('.lie, [class*="lie"], .is-lie');
        result.liesDetected = liesEls.length;

        // Get fingerprint hash
        const fpEl = document.querySelector('.fingerprint, .fp-hash, [class*="hash"]');
        if (fpEl) result.fingerprint = fpEl.textContent.trim();

        // Get detailed results
        const sections = ['canvas', 'audio', 'webgl', 'fonts', 'navigator'];
        sections.forEach(section => {
            const el = document.querySelector(`[class*="${section}"], #${section}`);
            if (el) {
                result.details[section] = {
                    text: el.textContent.substring(0, 200),
                    hasLie: el.classList.contains('lie') || el.querySelector('.lie') !== null
                };
            }
        });

        return result;
    })()
    """)

    results["creepjs"] = data
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "creepjs.png"), full_page=True)
    print(f"    Trust Score: {data.get('trustScore', 'N/A')}%")
    print(f"    Lies Detected: {data.get('liesDetected', 'N/A')}")


async def test_browserleaks_canvas(tab, results: dict) -> None:
    """Test BrowserLeaks Canvas."""
    print("  Testing browserleaks.com/canvas...")
    await tab.get("https://browserleaks.com/canvas", timeout=60)
    await asyncio.sleep(5)

    data = await tab.eval("""
    (() => {
        const result = {
            canvasHash: null,
            webglHash: null,
            signature: null
        };

        // Look for hash values in the page
        const hashEls = document.querySelectorAll('[class*="hash"], .signature, td, .value');
        hashEls.forEach(el => {
            const text = el.textContent.trim();
            // SHA-256 hash pattern
            if (/^[a-f0-9]{64}$/i.test(text)) {
                if (!result.canvasHash) result.canvasHash = text;
                else if (!result.webglHash) result.webglHash = text;
            }
        });

        // Get signature if available
        const sigEl = document.querySelector('.canvas-signature, [id*="signature"]');
        if (sigEl) result.signature = sigEl.textContent.trim();

        return result;
    })()
    """)

    results["browserleaks_canvas"] = data
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "browserleaks_canvas.png"), full_page=True)
    canvas_hash = data.get('canvasHash') or 'N/A'
    print(f"    Canvas Hash: {canvas_hash[:16] if canvas_hash != 'N/A' else 'N/A'}...")


async def test_browserleaks_webgl(tab, results: dict) -> None:
    """Test BrowserLeaks WebGL."""
    print("  Testing browserleaks.com/webgl...")
    await tab.get("https://browserleaks.com/webgl", timeout=60)
    await asyncio.sleep(5)

    data = await tab.eval("""
    (() => {
        const result = {
            vendor: null,
            renderer: null,
            webgpuVendor: null,
            webgpuDevice: null
        };

        // Find WebGL info
        const rows = document.querySelectorAll('tr, .row, .info-row');
        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            const cells = row.querySelectorAll('td, .value');
            const value = cells.length > 1 ? cells[1].textContent.trim() : cells[0]?.textContent?.trim();

            if (text.includes('vendor') && !text.includes('webgpu')) {
                result.vendor = value;
            } else if (text.includes('renderer') && !text.includes('webgpu')) {
                result.renderer = value;
            } else if (text.includes('webgpu') && text.includes('vendor')) {
                result.webgpuVendor = value;
            } else if (text.includes('webgpu') && text.includes('device')) {
                result.webgpuDevice = value;
            }
        });

        return result;
    })()
    """)

    results["browserleaks_webgl"] = data
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "browserleaks_webgl.png"), full_page=True)
    print(f"    WebGL Vendor: {data.get('vendor', 'N/A')}")
    print(f"    WebGL Renderer: {data.get('renderer', 'N/A')}")
    print(f"    WebGPU Vendor: {data.get('webgpuVendor', 'N/A')}")


async def test_fingerprint_demo(tab, results: dict) -> None:
    """Test fingerprint.com/demo — Browser Smart Signals."""
    print("  Testing fingerprint.com/demo...")
    await tab.get("https://fingerprint.com/demo/", timeout=60)
    await asyncio.sleep(8)

    # Click on "Browser Smart Signals" tab
    try:
        smart_signals_btn = await tab.find("Browser Smart Signals", timeout=15)
        await smart_signals_btn.click()
        await asyncio.sleep(5)
    except TimeoutError:
        print("    WARNING: Could not find 'Browser Smart Signals' button")
        results["fingerprint_demo"] = {"status": "error", "error": "smart_signals_button_not_found"}
        await tab.screenshot(str(Path(__file__).parent / "screenshots" / "fingerprint_demo_smart_signals.png"), full_page=True)
        return

    data = await tab.eval("""
    (() => {
        const result = {
            suspect_score: null,
            developer_tools: null,
            bot_detected: null,
            browser_tampering: null,
            vm_detected: null,
            incognito: null,
            vpn: null,
            ip_geolocation: null,
            raw_signals: {}
        };

        const bodyText = document.body.innerText;

        // Extract Suspect Score (look for number near "Suspect Score")
        const scoreMatch = bodyText.match(/Suspect\\s*Score[\\s\\S]{0,50}?(\\d+)/i);
        if (scoreMatch) result.suspect_score = parseInt(scoreMatch[1]);

        // Extract Developer Tools Detection
        if (/Developer\\s*Tools[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
            result.developer_tools = false;
        } else if (/Developer\\s*Tools[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
            result.developer_tools = true;
        }

        // Extract Bot Detection
        if (/Bot\\s*Detection[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
            result.bot_detected = "notDetected";
        } else if (/Bot\\s*Detection[\\s\\S]{0,100}?(good|bad)/i.test(bodyText)) {
            result.bot_detected = bodyText.match(/Bot\\s*Detection[\\s\\S]{0,100}?(good|bad)/i)[1].toLowerCase();
        }

        // Extract Browser Tampering
        if (/Browser\\s*Tamper[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
            result.browser_tampering = false;
        } else if (/Browser\\s*Tamper[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
            result.browser_tampering = true;
        }

        // Extract VM Detection
        if (/Virtual\\s*Machine[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
            result.vm_detected = false;
        } else if (/Virtual\\s*Machine[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
            result.vm_detected = true;
        }

        // Extract Incognito Detection
        if (/Incognito[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
            result.incognito = false;
        } else if (/Incognito[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
            result.incognito = true;
        }

        // Extract all visible signal rows as raw data
        const rows = document.querySelectorAll('tr, [class*="signal"], [class*="row"], [data-testid]');
        rows.forEach(row => {
            const text = row.textContent.trim();
            if (text.length > 5 && text.length < 200) {
                const parts = text.split(/\\n|\\t/).map(p => p.trim()).filter(Boolean);
                if (parts.length >= 2) {
                    result.raw_signals[parts[0].substring(0, 50)] = parts.slice(1).join(' | ');
                }
            }
        });

        return result;
    })()
    """)

    results["fingerprint_demo"] = data if data else {"status": "error", "error": "eval_returned_none"}
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "fingerprint_demo_smart_signals.png"), full_page=True)

    if data:
        print(f"    Suspect Score: {data.get('suspect_score', 'N/A')}")
        print(f"    Developer Tools: {'DETECTED' if data.get('developer_tools') else 'Not detected'}")
        print(f"    Bot Detection: {data.get('bot_detected', 'N/A')}")
        print(f"    Browser Tampering: {'DETECTED' if data.get('browser_tampering') else 'Not detected'}")
        print(f"    VM Detection: {'DETECTED' if data.get('vm_detected') else 'Not detected'}")
        print(f"    Incognito: {'DETECTED' if data.get('incognito') else 'Not detected'}")


async def test_sannysoft(tab, results: dict) -> None:
    """Test bot.sannysoft.com — classic bot detection checks."""
    print("  Testing bot.sannysoft.com...")
    await tab.get("https://bot.sannysoft.com/", timeout=30)
    await asyncio.sleep(5)

    data = await tab.eval("""
    (() => {
        const result = { passed: 0, failed: 0, warnings: 0, details: {} };
        const rows = document.querySelectorAll('table tr');
        rows.forEach(row => {
            const cells = row.querySelectorAll('td');
            if (cells.length >= 2) {
                const name = cells[0].textContent.trim();
                const value = cells[1].textContent.trim();
                const classes = cells[1].className || '';
                let status = 'unknown';
                if (classes.includes('passed') || value.toLowerCase() === 'passed') {
                    status = 'passed';
                    result.passed++;
                } else if (classes.includes('failed') || value.toLowerCase() === 'failed') {
                    status = 'failed';
                    result.failed++;
                } else if (classes.includes('warn')) {
                    status = 'warning';
                    result.warnings++;
                }
                result.details[name] = { value, status };
            }
        });
        return result;
    })()
    """)

    results["sannysoft"] = data if data else {"status": "error"}
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "sannysoft.png"), full_page=True)

    if data:
        print(f"    Passed: {data.get('passed', 0)}, Failed: {data.get('failed', 0)}, Warnings: {data.get('warnings', 0)}")
        for name, info in data.get('details', {}).items():
            if info.get('status') == 'failed':
                print(f"    FAIL: {name} = {info.get('value')}")


async def run_tests(seed: int, chrome_path: str) -> dict:
    """Run all fingerprint tests with a specific seed."""
    results = {
        "seed": seed,
        "timestamp": datetime.now().isoformat(),
        "chrome_path": chrome_path,
    }

    # Create screenshots directory
    screenshots_dir = Path(__file__).parent / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    print(f"\nRunning tests with seed={seed}...")

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

        await test_fingerprintjs(tab, results)
        await test_creepjs(tab, results)
        await test_browserleaks_canvas(tab, results)
        await test_browserleaks_webgl(tab, results)
        await test_fingerprint_demo(tab, results)
        await test_sannysoft(tab, results)

    finally:
        await browser.close()

    return results


async def compare_seeds(seeds: list[int], chrome_path: str) -> None:
    """Run tests with multiple seeds and compare results."""
    all_results = []

    for seed in seeds:
        results = await run_tests(seed, chrome_path)
        all_results.append(results)

        # Save individual result
        output_file = Path(__file__).parent / f"results_seed_{seed}.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  Results saved to {output_file}")

    # Compare results
    print("\n" + "="*60)
    print("COMPARISON REPORT")
    print("="*60)

    if len(all_results) >= 2:
        r1, r2 = all_results[0], all_results[1]

        print(f"\nSeed {r1['seed']} vs Seed {r2['seed']}:")

        # Canvas hash comparison
        c1 = r1.get("browserleaks_canvas", {}).get("canvasHash")
        c2 = r2.get("browserleaks_canvas", {}).get("canvasHash")
        if c1 and c2:
            status = "PASS (different)" if c1 != c2 else "FAIL (same)"
            print(f"  Canvas Hash: {status}")

        # CreepJS comparison
        t1 = r1.get("creepjs", {}).get("trustScore")
        t2 = r2.get("creepjs", {}).get("trustScore")
        if t1 is not None:
            print(f"  CreepJS Trust: Seed {r1['seed']}={t1}%, Seed {r2['seed']}={t2}%")

        l1 = r1.get("creepjs", {}).get("liesDetected", 0)
        l2 = r2.get("creepjs", {}).get("liesDetected", 0)
        print(f"  Lies Detected: Seed {r1['seed']}={l1}, Seed {r2['seed']}={l2}")

    # Stability check (run same seed twice)
    print("\n" + "="*60)
    print("STABILITY CHECK")
    print("="*60)

    seed = seeds[0]
    print(f"\nRunning seed {seed} twice to verify determinism...")
    r1 = await run_tests(seed, chrome_path)
    r2 = await run_tests(seed, chrome_path)

    c1 = r1.get("browserleaks_canvas", {}).get("canvasHash")
    c2 = r2.get("browserleaks_canvas", {}).get("canvasHash")
    if c1 and c2:
        status = "PASS (identical)" if c1 == c2 else "FAIL (different)"
        print(f"  Canvas Hash Stability: {status}")

    # Save comparison report
    report = {
        "seeds_tested": seeds,
        "results": all_results,
        "stability": {
            "seed": seed,
            "canvas_hash_run1": c1,
            "canvas_hash_run2": c2,
            "stable": c1 == c2 if c1 and c2 else None,
        }
    }

    report_file = Path(__file__).parent / "comparison_report.json"
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to {report_file}")


async def main():
    parser = argparse.ArgumentParser(description="Test chromium-telluride fingerprinting")
    parser.add_argument("--seed", type=int, default=42069, help="Fingerprint seed")
    parser.add_argument("--seeds", type=str, help="Comma-separated seeds for comparison (e.g., 42069,99999)")
    parser.add_argument("--chrome", type=str, default=CHROMIUM_TELLURIDE_PATH, help="Chrome executable path")
    args = parser.parse_args()

    if args.seeds:
        seeds = [int(s.strip()) for s in args.seeds.split(",")]
        await compare_seeds(seeds, args.chrome)
    else:
        results = await run_tests(args.seed, args.chrome)
        output_file = Path(__file__).parent / f"results_seed_{args.seed}.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
