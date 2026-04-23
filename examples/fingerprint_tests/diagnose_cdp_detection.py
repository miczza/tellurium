#!/usr/bin/env python3
"""
C4.7 Diagnostic: identify which CDP detection vectors are active.

Tests 3 known detection techniques, then visits fingerprint.com/demo
to extract the actual Smart Signals and Suspect Score.

Usage:
    python diagnose_cdp_detection.py [--chrome PATH]
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tellurium import Browser


CHROMIUM_TELLURIDE_PATH = "/home/miczza/PycharmProjects/chromium-telluride/src/out/Release/chrome"
SEED = 42069


async def main():
    chrome_path = CHROMIUM_TELLURIDE_PATH
    if len(sys.argv) > 1 and sys.argv[1] == "--chrome":
        chrome_path = sys.argv[2]

    print("=" * 60)
    print("C4.7 CDP DETECTION DIAGNOSTIC")
    print("=" * 60)
    print(f"Chrome: {chrome_path}")
    print(f"Seed: {SEED}")
    print(f"Time: {datetime.now().isoformat()}")

    browser = await Browser.launch(
        headless=False,
        executable=chrome_path,
        args=[
            f"--fingerprint={SEED}",
            "--fingerprint-platform=linux",
            "--no-sandbox",
            "--window-size=1920,1080",
        ],
    )

    results = {}

    try:
        tab = await browser.new_tab()

        # ── Phase 1: CDP Detection Vector Tests ──────────────────
        print("\n[1/2] CDP DETECTION VECTOR TESTS")
        print("-" * 40)

        await tab.get("data:text/html,<!DOCTYPE html><html><body><h1>CDP Diagnostic</h1></body></html>")
        await asyncio.sleep(1)

        vectors = await tab.eval("""
        (() => {
            const results = {};

            // Test 1: Error.stack getter trap
            // When CDP Inspector is active and processes console.debug(error),
            // it calls object->Get("stack") which triggers user-defined getters.
            try {
                let stackDetected = false;
                const e = new Error();
                Object.defineProperty(e, 'stack', {
                    configurable: false,
                    enumerable: false,
                    get() { stackDetected = true; return ''; },
                });
                console.debug(e);
                results.errorStackGetter = stackDetected;
            } catch (ex) {
                results.errorStackGetter = 'error: ' + ex.message;
            }

            // Test 2: Proxy prototype ownKeys trap
            // When Inspector serializes console args, it enumerates keys on
            // prototypes. If a prototype is a Proxy, ownKeys trap fires.
            try {
                let proxyDetected = false;
                const trap = new Proxy({}, {
                    ownKeys() { proxyDetected = true; return []; },
                });
                const obj = Object.create(trap);
                console.groupEnd(obj);
                results.proxyOwnKeys = proxyDetected;
            } catch (ex) {
                results.proxyOwnKeys = 'error: ' + ex.message;
            }

            // Test 3: Direct Proxy (not prototype chain)
            try {
                let directProxyDetected = false;
                const proxy = new Proxy({}, {
                    ownKeys() { directProxyDetected = true; return []; },
                    getOwnPropertyDescriptor() { directProxyDetected = true; return undefined; },
                });
                console.debug(proxy);
                results.directProxy = directProxyDetected;
            } catch (ex) {
                results.directProxy = 'error: ' + ex.message;
            }

            // Test 4: Error.stack via prototype chain (bypasses V8 May 2025 fix)
            try {
                let protoStackDetected = false;
                const base = {};
                Object.defineProperty(base, 'stack', {
                    configurable: true,
                    enumerable: false,
                    get() { protoStackDetected = true; return ''; },
                });
                const e = Object.create(base);
                // Make it look like an Error to the Inspector
                e.name = 'Error';
                e.message = 'test';
                console.debug(e);
                results.protoChainStackGetter = protoStackDetected;
            } catch (ex) {
                results.protoChainStackGetter = 'error: ' + ex.message;
            }

            // Test 5: Debugger statement timing
            try {
                const t0 = performance.now();
                debugger;
                const t1 = performance.now();
                results.debuggerDelayMs = t1 - t0;
            } catch (ex) {
                results.debuggerDelayMs = 'error: ' + ex.message;
            }

            // Test 6: console.profiles existence
            try {
                results.consoleProfiles = typeof console.profiles !== 'undefined';
            } catch (ex) {
                results.consoleProfiles = 'error: ' + ex.message;
            }

            // Test 7: Proxy get trap on console arg
            try {
                let getDetected = false;
                const trap = new Proxy({}, {
                    get(target, prop) {
                        if (prop === 'stack' || prop === 'message') {
                            getDetected = true;
                        }
                        return Reflect.get(target, prop);
                    },
                });
                const obj = Object.create(trap);
                console.debug(obj);
                results.proxyGetTrap = getDetected;
            } catch (ex) {
                results.proxyGetTrap = 'error: ' + ex.message;
            }

            return results;
        })()
        """)

        results["cdp_vectors"] = vectors
        print(f"  Error.stack getter:        {vectors.get('errorStackGetter')}")
        print(f"  Proxy ownKeys (prototype): {vectors.get('proxyOwnKeys')}")
        print(f"  Proxy ownKeys (direct):    {vectors.get('directProxy')}")
        print(f"  Proto-chain stack getter:  {vectors.get('protoChainStackGetter')}")
        print(f"  Debugger delay:            {vectors.get('debuggerDelayMs', 'N/A')}ms")
        print(f"  console.profiles:          {vectors.get('consoleProfiles')}")
        print(f"  Proxy get trap:            {vectors.get('proxyGetTrap')}")

        active_vectors = [k for k, v in vectors.items() if v is True]
        if active_vectors:
            print(f"\n  ACTIVE VECTORS: {', '.join(active_vectors)}")
        else:
            print(f"\n  No CDP detection vectors active!")

        # ── Phase 2: fingerprint.com/demo Smart Signals ──────────
        print("\n[2/2] FINGERPRINT.COM/DEMO SMART SIGNALS")
        print("-" * 40)

        print("  Navigating to fingerprint.com/demo...")
        await tab.get("https://fingerprint.com/demo/", timeout=60)
        await asyncio.sleep(10)

        # Dump all clickable/tab text to find the right Smart Signals label
        tab_labels = await tab.eval("""
        (() => {
            const labels = [];
            // Look for tab-like elements: buttons, links, tab roles, nav items
            const candidates = document.querySelectorAll(
                'button, a, [role="tab"], [class*="tab"], [class*="Tab"], nav *, [class*="nav"] *'
            );
            candidates.forEach(el => {
                const text = el.textContent.trim();
                if (text.length > 2 && text.length < 80) {
                    labels.push({
                        text: text,
                        tag: el.tagName,
                        className: (el.className || '').toString().substring(0, 80),
                    });
                }
            });
            return labels;
        })()
        """)
        print(f"  Found {len(tab_labels or [])} clickable elements. Tab-like labels:")
        for item in (tab_labels or []):
            text = item.get("text", "")
            if any(kw in text.lower() for kw in ["smart", "signal", "browser", "geoloc", "identif", "visitor", "finger"]):
                print(f"    -> '{text}' ({item.get('tag')} class={item.get('className', '')[:40]})")

        # Try multiple text variations to find the Smart Signals tab
        # "BROWSER SMART SIGNALS" is the exact tab label (uppercase)
        smart_signals_texts = [
            "BROWSER SMART SIGNALS",
            "Browser Smart Signals",
            "Smart Signals",
        ]
        btn = None
        for text in smart_signals_texts:
            try:
                btn = await tab.find(text, timeout=5)
                print(f"  Found tab with text: '{text}'. Clicking...")
                break
            except TimeoutError:
                continue

        if btn:
            await btn.click()
            await asyncio.sleep(8)
        else:
            print("  Could not find Smart Signals tab by text. Trying to click all tabs...")
            # Try clicking each tab-like element
            all_tabs = await tab.eval("""
            (() => {
                const tabs = document.querySelectorAll('[role="tab"], [class*="tab"], [class*="Tab"]');
                return Array.from(tabs).map((t, i) => ({
                    index: i,
                    text: t.textContent.trim().substring(0, 60),
                }));
            })()
            """)
            print(f"  Tab elements found: {json.dumps(all_tabs, indent=2)}")
            screenshots = Path(__file__).parent / "screenshots"
            screenshots.mkdir(exist_ok=True)
            await tab.screenshot(str(screenshots / "diagnose_no_button.png"), full_page=True)
            # Continue anyway — extract whatever is visible

        # Extract Smart Signals data
        print("  Extracting Smart Signals data...")
        signals = await tab.eval("""
        (() => {
            const result = {
                suspect_score: null,
                developer_tools: null,
                bot_detected: null,
                browser_tampering: null,
                vm_detected: null,
                incognito: null,
                vpn: null,
                privacy_settings: null,
                raw_text: '',
                raw_signals: {}
            };

            const bodyText = document.body.innerText;
            result.raw_text = bodyText.substring(0, 3000);

            // Suspect Score
            const scoreMatch = bodyText.match(/Suspect\\s*Score[\\s\\S]{0,50}?(\\d+)/i);
            if (scoreMatch) result.suspect_score = parseInt(scoreMatch[1]);

            // Developer Tools Detection
            if (/Developer\\s*Tools[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
                result.developer_tools = false;
            } else if (/Developer\\s*Tools[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
                result.developer_tools = true;
            }

            // Bot Detection
            if (/Bot[\\s\\S]{0,30}?Detection[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
                result.bot_detected = "notDetected";
            } else if (/Bot[\\s\\S]{0,30}?Detection[\\s\\S]{0,100}?(good|bad)/i.test(bodyText)) {
                result.bot_detected = bodyText.match(/Bot[\\s\\S]{0,30}?Detection[\\s\\S]{0,100}?(good|bad)/i)[1];
            }

            // Browser Tampering
            if (/Browser\\s*Tamper[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
                result.browser_tampering = false;
            } else if (/Browser\\s*Tamper[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
                result.browser_tampering = true;
            }

            // VM Detection
            if (/Virtual\\s*Machine[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
                result.vm_detected = false;
            } else if (/Virtual\\s*Machine[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
                result.vm_detected = true;
            }

            // Incognito
            if (/Incognito[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
                result.incognito = false;
            } else if (/Incognito[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
                result.incognito = true;
            }

            // VPN
            if (/VPN[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
                result.vpn = false;
            } else if (/VPN[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
                result.vpn = true;
            }

            // Privacy Settings
            if (/Privacy[\\s\\S]{0,30}?Settings[\\s\\S]{0,100}?Not\\s*detected/i.test(bodyText)) {
                result.privacy_settings = false;
            } else if (/Privacy[\\s\\S]{0,30}?Settings[\\s\\S]{0,100}?Detected/i.test(bodyText)) {
                result.privacy_settings = true;
            }

            // Extract all visible signal rows
            const rows = document.querySelectorAll('tr, [class*="signal"], [class*="row"], [data-testid], li, dt, dd');
            rows.forEach(row => {
                const text = row.textContent.trim();
                if (text.length > 3 && text.length < 300) {
                    const parts = text.split(/\\n|\\t/).map(p => p.trim()).filter(Boolean);
                    if (parts.length >= 2) {
                        result.raw_signals[parts[0].substring(0, 60)] = parts.slice(1).join(' | ');
                    }
                }
            });

            return result;
        })()
        """)

        results["fingerprint_demo"] = signals

        # Screenshot
        screenshots = Path(__file__).parent / "screenshots"
        screenshots.mkdir(exist_ok=True)
        await tab.screenshot(str(screenshots / "diagnose_smart_signals.png"), full_page=True)

        if signals:
            print(f"\n  Suspect Score:     {signals.get('suspect_score', 'N/A')}")
            print(f"  Developer Tools:   {'DETECTED' if signals.get('developer_tools') else 'Not detected' if signals.get('developer_tools') is False else 'N/A'}")
            print(f"  Bot Detection:     {signals.get('bot_detected', 'N/A')}")
            print(f"  Browser Tampering: {'DETECTED' if signals.get('browser_tampering') else 'Not detected' if signals.get('browser_tampering') is False else 'N/A'}")
            print(f"  VM Detection:      {'DETECTED' if signals.get('vm_detected') else 'Not detected' if signals.get('vm_detected') is False else 'N/A'}")
            print(f"  Incognito:         {'DETECTED' if signals.get('incognito') else 'Not detected' if signals.get('incognito') is False else 'N/A'}")
            print(f"  VPN:               {'DETECTED' if signals.get('vpn') else 'Not detected' if signals.get('vpn') is False else 'N/A'}")
            print(f"  Privacy Settings:  {'DETECTED' if signals.get('privacy_settings') else 'Not detected' if signals.get('privacy_settings') is False else 'N/A'}")

            if signals.get("raw_signals"):
                print(f"\n  Raw signals ({len(signals['raw_signals'])} entries):")
                for k, v in list(signals["raw_signals"].items())[:20]:
                    print(f"    {k}: {v[:80]}")

    finally:
        await browser.close()

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("DIAGNOSIS SUMMARY")
    print("=" * 60)

    vectors = results.get("cdp_vectors", {})
    active = [k for k, v in vectors.items() if v is True]
    fd = results.get("fingerprint_demo", {})

    if active:
        print(f"\nACTIVE CDP VECTORS: {', '.join(active)}")
        print("These vectors allow fingerprint.com to detect CDP activity.")
        if "errorStackGetter" in active:
            print("  -> Error.stack getter: V8 Inspector reads error.stack triggering user getters")
        if "proxyOwnKeys" in active:
            print("  -> Proxy ownKeys: Inspector enumerates prototype keys triggering ownKeys trap")
        if "directProxy" in active:
            print("  -> Direct Proxy: Inspector enumerates direct Proxy keys")
        if "protoChainStackGetter" in active:
            print("  -> Proto-chain stack: Stack getter on prototype bypasses V8 fix")
        if "proxyGetTrap" in active:
            print("  -> Proxy get trap: Inspector reads properties triggering get trap")
    else:
        print("\nNo CDP detection vectors active in local tests.")
        print("If fingerprint.com still detects, they may use server-side analysis.")

    score = fd.get("suspect_score")
    devtools = fd.get("developer_tools")
    print(f"\nFingerprint.com results:")
    print(f"  Suspect Score: {score}")
    print(f"  Developer Tools Detected: {devtools}")

    if score is not None and score > 0:
        print(f"\n  Score breakdown hypothesis (weight table):")
        if devtools:
            print(f"    Developer Tools Detection: +8")
        if fd.get("browser_tampering"):
            print(f"    Browser Tampering: +8")
        if fd.get("incognito"):
            print(f"    Incognito: +4")
        if fd.get("privacy_settings"):
            print(f"    Privacy Settings: +6")
        remaining = score
        if devtools:
            remaining -= 8
        if remaining > 0:
            print(f"    Unexplained: +{remaining}")

    # Save full results
    output = Path(__file__).parent / "diagnose_results.json"
    with open(output, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull results saved to {output}")
    print(f"Screenshot saved to screenshots/diagnose_smart_signals.png")


if __name__ == "__main__":
    asyncio.run(main())
