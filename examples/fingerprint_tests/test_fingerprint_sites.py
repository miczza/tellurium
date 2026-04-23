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
    if not data.get('visitorId'):
        print("    WARNING: No Visitor ID captured — FingerprintJS may have failed to load")


async def test_creepjs(tab, results: dict) -> None:
    """Test CreepJS — headless/stealth detection with signal breakdown."""
    print("  Testing creepjs.com...")
    await tab.get("https://abrahamjuliot.github.io/creepjs/", timeout=60)
    await asyncio.sleep(15)

    data = await tab.eval("""
    (async () => {
        await new Promise(r => setTimeout(r, 5000));

        const result = {
            trust_score: null,
            lies_detected: 0,
            headless_pct: null,
            stealth_pct: null,
            like_headless_pct: null,
            fingerprint_id: null,
            signal_breakdown: {}
        };

        const bodyText = document.body.innerText;

        // Extract percentages from page text
        const headlessMatch = bodyText.match(/(\\d+)%\\s*headless/i);
        if (headlessMatch) result.headless_pct = parseInt(headlessMatch[1]);

        const stealthMatch = bodyText.match(/(\\d+)%\\s*stealth/i);
        if (stealthMatch) result.stealth_pct = parseInt(stealthMatch[1]);

        const likeHeadlessMatch = bodyText.match(/(\\d+)%\\s*like\\s*headless/i);
        if (likeHeadlessMatch) result.like_headless_pct = parseInt(likeHeadlessMatch[1]);

        // Trust score
        const trustMatch = bodyText.match(/trust[:\\s]*?(\\d+)%/i);
        if (trustMatch) result.trust_score = parseInt(trustMatch[1]);

        // Lies count
        const liesMatch = bodyText.match(/lies\\s*\\((\\d+)\\)/i);
        if (liesMatch) result.lies_detected = parseInt(liesMatch[1]);
        if (result.lies_detected === 0) {
            const altMatch = bodyText.match(/(\\d+)\\s*lie/i);
            if (altMatch) result.lies_detected = parseInt(altMatch[1]);
        }

        // Fingerprint ID
        const fpMatch = bodyText.match(/([a-f0-9]{16,})/i);
        if (fpMatch) result.fingerprint_id = fpMatch[1];

        // Try to get internal signal breakdown
        try {
            if (window.Fingerprint) {
                const fp = window.Fingerprint;
                if (fp.headless) result.signal_breakdown.headless = fp.headless;
                if (fp.stealth) result.signal_breakdown.stealth = fp.stealth;
                if (fp.likeHeadless) result.signal_breakdown.likeHeadless = fp.likeHeadless;
            }
        } catch (e) {}

        // Count lie elements in DOM
        const lieElements = document.querySelectorAll('[class*="lies"], .is-lie, .lie-count');
        if (lieElements.length > 0 && result.lies_detected === 0) {
            result.lies_detected = lieElements.length;
        }

        return result;
    })()
    """)

    results["creepjs"] = data if data else {"status": "error"}
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "creepjs.png"), full_page=True)

    if data:
        print(f"    Trust Score: {data.get('trust_score', 'N/A')}%")
        print(f"    Headless: {data.get('headless_pct', 'N/A')}%")
        print(f"    Stealth: {data.get('stealth_pct', 'N/A')}%")
        print(f"    Like Headless: {data.get('like_headless_pct', 'N/A')}%")
        print(f"    Lies Detected: {data.get('lies_detected', 'N/A')}")
        print(f"    FP ID: {(data.get('fingerprint_id') or 'N/A')[:16]}...")


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
    if not data.get('canvasHash'):
        print("    WARNING: No canvas hash captured — canvas fingerprinting may not be working")


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
    if data.get('renderer') and 'ANGLE' in data.get('renderer', ''):
        print(f"    Renderer is spoofed (ANGLE prefix present)")
    elif data.get('renderer'):
        print(f"    WARNING: Renderer may not be spoofed: {data.get('renderer')}")


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


async def test_browserscan(tab, results: dict) -> None:
    """Test browserscan.net — comprehensive browser fingerprint scan."""
    print("  Testing browserscan.net...")
    await tab.get("https://www.browserscan.net/", timeout=30)
    await asyncio.sleep(8)

    data = await tab.eval("""
    (() => {
        const result = { bot_detected: null, details: {} };
        const bodyText = document.body.innerText;

        // Check for bot/automation detection
        if (/bot/i.test(bodyText) && /detected/i.test(bodyText)) {
            result.bot_detected = true;
        } else {
            result.bot_detected = false;
        }

        // Extract key-value pairs from the page
        const rows = document.querySelectorAll('tr, [class*="item"], [class*="row"], [class*="info"]');
        rows.forEach(row => {
            const text = row.textContent.trim();
            if (text.length > 3 && text.length < 300) {
                const parts = text.split(/\\n|\\t|:\\s/).map(p => p.trim()).filter(Boolean);
                if (parts.length >= 2) {
                    const key = parts[0].substring(0, 40);
                    result.details[key] = parts.slice(1).join(' ');
                }
            }
        });

        // Extract specific signals
        const ua = bodyText.match(/User\\s*Agent[\\s:]+(.+?)(?:\\n|$)/i);
        if (ua) result.details['UserAgent'] = ua[1].trim().substring(0, 120);

        const webgl = bodyText.match(/WebGL\\s*Renderer[\\s:]+(.+?)(?:\\n|$)/i);
        if (webgl) result.details['WebGLRenderer'] = webgl[1].trim();

        return result;
    })()
    """)

    results["browserscan"] = data if data else {"status": "error"}
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "browserscan.png"), full_page=True)

    if data:
        print(f"    Bot Detected: {data.get('bot_detected', 'N/A')}")
        details = data.get('details', {})
        if 'UserAgent' in details:
            print(f"    User Agent: {details['UserAgent'][:60]}...")
        if 'WebGLRenderer' in details:
            print(f"    WebGL Renderer: {details['WebGLRenderer']}")


async def test_fingerprint_scan(tab, results: dict) -> None:
    """Test fingerprint-scan.com — bot risk score + headless signals."""
    print("  Testing fingerprint-scan.com...")
    await tab.get("https://fingerprint-scan.com/", timeout=30)
    await asyncio.sleep(20)  # Castle.js needs time to compute

    data = await tab.eval("""
    (() => {
        const result = { bot_risk_score: null, signals: {}, bot_tests: {} };

        // Extract bot risk score
        const scoreEl = document.querySelector('#fingerprintScore, [class*="score"]');
        if (scoreEl) {
            const match = scoreEl.textContent.match(/([0-9.]+)/);
            if (match) result.bot_risk_score = parseFloat(match[1]);
        }

        // Extract headless detection signals via JS
        result.signals = {
            noTaskbar: window.screen.height === window.screen.availHeight,
            taskbarSize: window.screen.height - window.screen.availHeight,
            noContentIndex: typeof window.ContentIndex === 'undefined',
            noContactsManager: !('contacts' in navigator),
            noDownlinkMax: !navigator.connection || navigator.connection.downlinkMax === undefined,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            webdriver: navigator.webdriver,
            scrollbarWidth: (() => {
                const div = document.createElement('div');
                div.style.cssText = 'width:100px;height:100px;overflow:scroll;position:absolute;top:-9999px';
                document.body.appendChild(div);
                const w = div.offsetWidth - div.clientWidth;
                document.body.removeChild(div);
                return w;
            })(),
        };

        // Extract bot test results from page
        const bodyText = document.body.innerText;
        const tests = ['WebDriver', 'IsSeleniumChrome', 'CDPCheck', 'IsPlaywright'];
        tests.forEach(test => {
            const match = bodyText.match(new RegExp(test + '[\\\\s:]+([\\\\w]+)', 'i'));
            if (match) result.bot_tests[test] = match[1];
        });

        return result;
    })()
    """)

    results["fingerprint_scan"] = data if data else {"status": "error"}
    await tab.screenshot(str(Path(__file__).parent / "screenshots" / "fingerprint_scan.png"), full_page=True)

    if data:
        print(f"    Bot Risk Score: {data.get('bot_risk_score', 'N/A')}")
        signals = data.get('signals', {})
        print(f"    navigator.webdriver: {signals.get('webdriver', 'N/A')}")
        print(f"    noTaskbar: {signals.get('noTaskbar', 'N/A')}")
        print(f"    scrollbarWidth: {signals.get('scrollbarWidth', 'N/A')}")
        for test, val in data.get('bot_tests', {}).items():
            print(f"    {test}: {val}")


SITE_TESTS = {
    "fingerprintjs": test_fingerprintjs,
    "creepjs": test_creepjs,
    "browserleaks_canvas": test_browserleaks_canvas,
    "browserleaks_webgl": test_browserleaks_webgl,
    "fingerprint_demo": test_fingerprint_demo,
    "sannysoft": test_sannysoft,
    "browserscan": test_browserscan,
    "fingerprint_scan": test_fingerprint_scan,
}


def validate_results(results: dict) -> tuple[list[str], list[str]]:
    """Validate results against CRITICAL and WARNING thresholds.

    Returns (critical_failures, warnings).
    """
    critical = []
    warnings = []

    # fingerprint.com/demo checks
    fd = results.get("fingerprint_demo", {})
    if fd.get("developer_tools") is True:
        critical.append("Developer Tools DETECTED by fingerprint.com")
    if fd.get("bot_detected") and fd["bot_detected"] != "notDetected":
        critical.append(f"Bot DETECTED by fingerprint.com: {fd['bot_detected']}")
    if fd.get("browser_tampering") is True:
        critical.append("Browser Tampering DETECTED by fingerprint.com")
    if fd.get("vm_detected") is True:
        critical.append("VM DETECTED by fingerprint.com")
    score = fd.get("suspect_score")
    if score is not None and score > 0:
        warnings.append(f"Suspect Score = {score} (target: 0)")

    # sannysoft checks
    ss = results.get("sannysoft", {})
    if ss.get("failed", 0) > 0:
        for name, info in ss.get("details", {}).items():
            if info.get("status") == "failed":
                critical.append(f"sannysoft FAIL: {name} = {info.get('value')}")

    # CreepJS checks
    cj = results.get("creepjs", {})
    if cj.get("headless_pct") is not None and cj["headless_pct"] > 0:
        warnings.append(f"CreepJS headless = {cj['headless_pct']}% (target: 0%)")
    if cj.get("stealth_pct") is not None and cj["stealth_pct"] > 0:
        warnings.append(f"CreepJS stealth = {cj['stealth_pct']}% (target: 0%)")
    if cj.get("lies_detected", 0) > 0:
        critical.append(f"CreepJS lies detected: {cj['lies_detected']}")

    # fingerprint-scan checks
    fs = results.get("fingerprint_scan", {})
    signals = fs.get("signals", {})
    if signals.get("webdriver") is True:
        critical.append("navigator.webdriver = true")

    return critical, warnings


async def run_tests(seed: int, chrome_path: str, **kwargs) -> dict:
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

        site_filter = kwargs.get("site_filter")
        tests_to_run = SITE_TESTS
        if site_filter:
            if site_filter not in SITE_TESTS:
                raise ValueError(f"Unknown site: {site_filter}. Available: {', '.join(SITE_TESTS)}")
            tests_to_run = {site_filter: SITE_TESTS[site_filter]}

        for name, test_fn in tests_to_run.items():
            try:
                await test_fn(tab, results)
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"    ERROR: {name}: {e}")

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
    parser.add_argument("--site", type=str, help="Run only a specific site test (e.g., fingerprint_demo, creepjs)")
    args = parser.parse_args()

    if args.seeds:
        seeds = [int(s.strip()) for s in args.seeds.split(",")]
        await compare_seeds(seeds, args.chrome)
    else:
        results = await run_tests(args.seed, args.chrome, site_filter=args.site)

        # Validate
        critical, warnings = validate_results(results)

        if critical:
            print("\nCRITICAL FAILURES:")
            for c in critical:
                print(f"  FAIL: {c}", file=sys.stderr)
        if warnings:
            print("\nWARNINGS:")
            for w in warnings:
                print(f"  WARN: {w}", file=sys.stderr)
        if not critical and not warnings:
            print("\nAll checks PASSED")

        output_file = Path(__file__).parent / f"results_seed_{args.seed}.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {output_file}")

        sys.exit(1 if critical else 0)


if __name__ == "__main__":
    asyncio.run(main())
