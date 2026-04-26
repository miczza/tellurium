#!/usr/bin/env python3
"""
Comparative detection test across browser automation frameworks.

Frameworks tested:
- tellurium (ours)
- selenium
- playwright
- playwright-stealth
- nodriver
- undetected-chromedriver
- DrissionPage
- pydoll

Sites: bot.sannysoft.com, CreepJS, BrowserLeaks Canvas/WebGL, browserscan.net

Usage:
    # Stock Chrome (all frameworks, default binary)
    python comparative_test.py

    # Patched chromium-telluride (only makes sense for tellurium + maybe others)
    python comparative_test.py --chrome-path /path/to/chromium-telluride/chrome

    # Subset of frameworks
    python comparative_test.py --frameworks tellurium,playwright_stealth,nodriver
"""

import asyncio
import json
import time
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

DEFAULT_CHROME = "/usr/bin/google-chrome-stable"
SCREENSHOTS_DIR = Path(__file__).parent / "screenshots" / "comparative"
RESULTS_FILE = Path(__file__).parent / "comparative_results.json"

JS_SANNYSOFT = """
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
                status = 'passed'; result.passed++;
            } else if (classes.includes('failed') || value.toLowerCase() === 'failed') {
                status = 'failed'; result.failed++;
            } else if (classes.includes('warn')) {
                status = 'warning'; result.warnings++;
            }
            result.details[name] = { value, status };
        }
    });
    return result;
})()
"""

JS_CREEPJS = """
(() => {
    const result = {
        lies_detected: 0,
        headless_pct: null, like_headless_pct: null, stealth_pct: null,
        version: { source: 'unknown', value: null }
    };
    const bodyText = document.body.innerText;
    // CreepJS emits "<n>% headless: <hash>" and "<n>% like headless: <hash>".
    // The two are disjoint: \\s*headless requires whitespace-only between %
    // and headless, so 'like' (non-whitespace) prevents the headless regex
    // from matching the like-headless line.
    const hm = bodyText.match(/(\\d+)%\\s*headless/i);
    if (hm) result.headless_pct = parseInt(hm[1]);
    const lhm = bodyText.match(/(\\d+)%\\s*like\\s*headless/i);
    if (lhm) result.like_headless_pct = parseInt(lhm[1]);
    const sm = bodyText.match(/(\\d+)%\\s*stealth/i);
    if (sm) result.stealth_pct = parseInt(sm[1]);
    const lm = bodyText.match(/lies\\s*\\((\\d+)\\)/i);
    if (lm) result.lies_detected = parseInt(lm[1]);
    if (result.lies_detected === 0) {
        const am = bodyText.match(/(\\d+)\\s*lie/i);
        if (am) result.lies_detected = parseInt(am[1]);
    }
    // T7.6 F3: best-effort capture of the CreepJS bundle version for triage.
    // Three-strategy fallback chain; output is always a serialisable
    // {source, value} object.
    const meta = document.querySelector(
        'meta[name="version"], meta[name="creepjs-version"]');
    if (meta) {
        result.version = { source: 'meta', value: meta.content };
    } else {
        const script = document.querySelector('script[src*="creep"]');
        if (script) {
            result.version = { source: 'script-src', value: script.src };
        } else if (typeof window.creepjsVersion !== 'undefined') {
            result.version = { source: 'global', value: String(window.creepjsVersion) };
        }
    }
    return result;
})()
"""

JS_CANVAS = """
(() => {
    const result = { canvasHash: null, uniqueness: null };
    const hashEl = document.getElementById('canvas-hash');
    if (hashEl) result.canvasHash = hashEl.textContent.trim();
    const ratioEl = document.getElementById('canvas-ratio');
    if (ratioEl) result.uniqueness = ratioEl.textContent.trim();
    return result;
})()
"""

JS_WEBGL = """
(() => {
    const result = { vendor: null, renderer: null };
    const vendorEl = document.getElementById('UNMASKED_VENDOR_WEBGL');
    if (vendorEl) result.vendor = vendorEl.textContent.trim();
    const rendererEl = document.getElementById('UNMASKED_RENDERER_WEBGL');
    if (rendererEl) result.renderer = rendererEl.textContent.trim();
    return result;
})()
"""

JS_BROWSERSCAN = """
(() => {
    const result = { bot_detected: null, webdriver: null, details: {} };
    const bodyText = document.body.innerText;
    result.webdriver = navigator.webdriver;
    if (/bot/i.test(bodyText) && /detected/i.test(bodyText)) {
        result.bot_detected = true;
    } else {
        result.bot_detected = false;
    }
    return result;
})()
"""

JS_WEBDRIVER_CHECK = "(() => ({ webdriver: navigator.webdriver, chrome: !!window.chrome, permissions: typeof navigator.permissions }))()"

SITES = {
    "sannysoft": {"url": "https://bot.sannysoft.com/", "wait": 5, "js": JS_SANNYSOFT},
    "creepjs": {"url": "https://abrahamjuliot.github.io/creepjs/", "wait": 25, "js": JS_CREEPJS},
    "browserleaks_canvas": {"url": "https://browserleaks.com/canvas", "wait": 5, "js": JS_CANVAS},
    "browserleaks_webgl": {"url": "https://browserleaks.com/webgl", "wait": 5, "js": JS_WEBGL},
    "browserscan": {"url": "https://www.browserscan.net/", "wait": 8, "js": JS_BROWSERSCAN},
}

# ═══════════════════════════════════════════════════════════════════════
# Tellurium
# ═══════════════════════════════════════════════════════════════════════

async def run_tellurium(chrome_path: str) -> dict:
    from tellurium import Browser

    import os as _os
    fp_seed = _os.environ.get("TELLURIUM_FP_SEED")
    extra_args = []
    if fp_seed and "chromium-telluride" in chrome_path:
        extra_args = [f"--fingerprint={fp_seed}", "--fingerprint-platform=linux"]

    print(f"\n[TELLURIUM] chrome={chrome_path} fp_seed={fp_seed or 'none'}")
    results = {"framework": "tellurium", "chrome": chrome_path, "fp_seed": fp_seed}
    t0 = time.time()

    # Default stealth=True (post-T7). Env var opt-out for A/B testing.
    use_stealth = _os.environ.get("TELLURIUM_STEALTH_FLAG", "1") != "0"
    browser = await Browser.launch(
        headless=False,
        executable=chrome_path,
        args=["--no-sandbox", "--window-size=1920,1080"] + extra_args,
        stealth=use_stealth,
    )
    print(f"[TELLURIUM] stealth={use_stealth}")

    try:
        tab = await browser.new_tab()
        await tab.get("about:blank")
        results["webdriver_check"] = await tab.eval(JS_WEBDRIVER_CHECK)

        for name, site in SITES.items():
            print(f"  [{name}]...", end=" ", flush=True)
            try:
                await tab.get(site["url"], timeout=60)
                await asyncio.sleep(site["wait"])
                data = await tab.eval(site["js"])
                results[name] = data if data else {"status": "error", "error": "eval None"}
                await tab.screenshot(str(SCREENSHOTS_DIR / f"tellurium_{name}.png"), full_page=True)
                print("OK")
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"ERROR: {e}")
    finally:
        await browser.close()

    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


# ═══════════════════════════════════════════════════════════════════════
# Selenium
# ═══════════════════════════════════════════════════════════════════════

async def run_selenium(chrome_path: str) -> dict:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    import chromedriver_autoinstaller

    print(f"\n[SELENIUM] chrome={chrome_path}")
    results = {"framework": "selenium", "chrome": chrome_path}
    t0 = time.time()

    chromedriver_autoinstaller.install()
    opts = Options()
    opts.binary_location = chrome_path
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=opts)

    try:
        driver.get("about:blank")
        results["webdriver_check"] = driver.execute_script("return " + JS_WEBDRIVER_CHECK.strip())

        for name, site in SITES.items():
            print(f"  [{name}]...", end=" ", flush=True)
            try:
                driver.get(site["url"])
                time.sleep(site["wait"])
                data = driver.execute_script("return " + site["js"].strip())
                results[name] = data if data else {"status": "error", "error": "eval None"}
                driver.save_screenshot(str(SCREENSHOTS_DIR / f"selenium_{name}.png"))
                print("OK")
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"ERROR: {e}")
    finally:
        driver.quit()

    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


# ═══════════════════════════════════════════════════════════════════════
# Playwright
# ═══════════════════════════════════════════════════════════════════════

async def run_playwright(chrome_path: str) -> dict:
    from playwright.async_api import async_playwright

    print(f"\n[PLAYWRIGHT] chrome={chrome_path}")
    results = {"framework": "playwright", "chrome": chrome_path}
    t0 = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=chrome_path, headless=False,
            args=["--no-sandbox", "--window-size=1920,1080"],
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        await page.goto("about:blank")
        results["webdriver_check"] = await page.evaluate(JS_WEBDRIVER_CHECK)

        for name, site in SITES.items():
            print(f"  [{name}]...", end=" ", flush=True)
            try:
                await page.goto(site["url"], timeout=60000)
                await asyncio.sleep(site["wait"])
                data = await page.evaluate(site["js"])
                results[name] = data if data else {"status": "error", "error": "eval None"}
                await page.screenshot(path=str(SCREENSHOTS_DIR / f"playwright_{name}.png"), full_page=True)
                print("OK")
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"ERROR: {e}")
        await browser.close()

    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


# ═══════════════════════════════════════════════════════════════════════
# Playwright + Stealth
# ═══════════════════════════════════════════════════════════════════════

async def run_playwright_stealth(chrome_path: str) -> dict:
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    print(f"\n[PLAYWRIGHT-STEALTH] chrome={chrome_path}")
    results = {"framework": "playwright_stealth", "chrome": chrome_path}
    t0 = time.time()

    stealth = Stealth()
    async with stealth.use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            executable_path=chrome_path, headless=False,
            args=["--no-sandbox", "--window-size=1920,1080"],
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        await page.goto("about:blank")
        results["webdriver_check"] = await page.evaluate(JS_WEBDRIVER_CHECK)

        for name, site in SITES.items():
            print(f"  [{name}]...", end=" ", flush=True)
            try:
                await page.goto(site["url"], timeout=60000)
                await asyncio.sleep(site["wait"])
                data = await page.evaluate(site["js"])
                results[name] = data if data else {"status": "error", "error": "eval None"}
                await page.screenshot(path=str(SCREENSHOTS_DIR / f"stealth_{name}.png"), full_page=True)
                print("OK")
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"ERROR: {e}")
        await browser.close()

    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


# ═══════════════════════════════════════════════════════════════════════
# Nodriver
# ═══════════════════════════════════════════════════════════════════════

async def run_nodriver(chrome_path: str) -> dict:
    import nodriver

    print(f"\n[NODRIVER] chrome={chrome_path}")
    results = {"framework": "nodriver", "chrome": chrome_path}
    t0 = time.time()

    browser = await nodriver.start(
        browser_executable_path=chrome_path,
        browser_args=["--no-sandbox", "--window-size=1920,1080"],
        headless=False,
        sandbox=False,
    )

    async def evaluate_json(tab, js: str):
        """Wrap JS to return JSON string, then parse in Python.
        Avoids RemoteObject dereferencing issues in nodriver 0.46."""
        wrapped = f"JSON.stringify(({js.strip()}))"
        raw = await tab.evaluate(wrapped)
        # nodriver may return RemoteObject or string
        val = getattr(raw, "value", raw)
        if val is None:
            return None
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return None
        return val

    try:
        tab = await browser.get("about:blank")
        wd = await evaluate_json(tab, JS_WEBDRIVER_CHECK)
        results["webdriver_check"] = wd if isinstance(wd, dict) else {"webdriver": None}

        for name, site in SITES.items():
            print(f"  [{name}]...", end=" ", flush=True)
            try:
                tab = await browser.get(site["url"])
                await asyncio.sleep(site["wait"])
                data = await evaluate_json(tab, site["js"])
                results[name] = data if data else {"status": "error", "error": "eval None"}
                try:
                    await tab.save_screenshot(str(SCREENSHOTS_DIR / f"nodriver_{name}.png"), full_page=True)
                except Exception:
                    pass
                print("OK")
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"ERROR: {e}")
    finally:
        try:
            browser.stop()
        except Exception:
            pass

    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


# ═══════════════════════════════════════════════════════════════════════
# undetected-chromedriver
# ═══════════════════════════════════════════════════════════════════════

async def run_undetected_chromedriver(chrome_path: str) -> dict:
    import undetected_chromedriver as uc

    print(f"\n[UNDETECTED-CHROMEDRIVER] chrome={chrome_path}")
    results = {"framework": "undetected_chromedriver", "chrome": chrome_path}
    t0 = time.time()

    opts = uc.ChromeOptions()
    opts.binary_location = chrome_path
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1920,1080")

    # Detect Chrome major version to match chromedriver
    import subprocess, re
    version_main = None
    try:
        v = subprocess.check_output([chrome_path, "--version"], text=True, timeout=5)
        m = re.search(r"(\d+)\.", v)
        if m:
            version_main = int(m.group(1))
    except Exception:
        pass

    driver = await asyncio.to_thread(
        lambda: uc.Chrome(options=opts, use_subprocess=True, version_main=version_main)
    )

    try:
        driver.get("about:blank")
        results["webdriver_check"] = driver.execute_script("return " + JS_WEBDRIVER_CHECK.strip())

        for name, site in SITES.items():
            print(f"  [{name}]...", end=" ", flush=True)
            try:
                driver.get(site["url"])
                time.sleep(site["wait"])
                data = driver.execute_script("return " + site["js"].strip())
                results[name] = data if data else {"status": "error", "error": "eval None"}
                driver.save_screenshot(str(SCREENSHOTS_DIR / f"uc_{name}.png"))
                print("OK")
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"ERROR: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


# ═══════════════════════════════════════════════════════════════════════
# DrissionPage
# ═══════════════════════════════════════════════════════════════════════

async def run_drissionpage(chrome_path: str) -> dict:
    from DrissionPage import ChromiumPage, ChromiumOptions

    print(f"\n[DRISSIONPAGE] chrome={chrome_path}")
    results = {"framework": "drissionpage", "chrome": chrome_path}
    t0 = time.time()

    opts = ChromiumOptions()
    opts.set_browser_path(chrome_path)
    opts.set_argument("--no-sandbox")
    opts.set_argument("--window-size=1920,1080")

    page = await asyncio.to_thread(lambda: ChromiumPage(addr_or_opts=opts))

    try:
        page.get("about:blank")
        # DrissionPage run_js supports async and returns value
        results["webdriver_check"] = page.run_js("return " + JS_WEBDRIVER_CHECK.strip())

        for name, site in SITES.items():
            print(f"  [{name}]...", end=" ", flush=True)
            try:
                page.get(site["url"])
                time.sleep(site["wait"])
                data = page.run_js("return " + site["js"].strip())
                results[name] = data if data else {"status": "error", "error": "eval None"}
                page.get_screenshot(path=str(SCREENSHOTS_DIR / f"drissionpage_{name}.png"), full_page=True)
                print("OK")
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"ERROR: {e}")
    finally:
        try:
            page.quit()
        except Exception:
            pass

    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


# ═══════════════════════════════════════════════════════════════════════
# pydoll
# ═══════════════════════════════════════════════════════════════════════

async def run_pydoll(chrome_path: str) -> dict:
    from pydoll.browser.chromium import Chrome
    from pydoll.browser.options import ChromiumOptions as POpts

    print(f"\n[PYDOLL] chrome={chrome_path}")
    results = {"framework": "pydoll", "chrome": chrome_path}
    t0 = time.time()

    opts = POpts()
    opts.binary_location = chrome_path
    opts.add_argument("--no-sandbox")
    opts.add_argument("--window-size=1920,1080")

    async def evaluate_json(tab, js: str):
        wrapped = f"JSON.stringify(({js.strip()}))"
        resp = await tab.execute_script(wrapped)
        if isinstance(resp, dict):
            val = resp.get("result", {}).get("result", {}).get("value")
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return None
            return val
        return resp

    async with Chrome(options=opts) as browser:
        tab = await browser.start()
        await tab.go_to("about:blank")
        wd = await evaluate_json(tab, JS_WEBDRIVER_CHECK)
        results["webdriver_check"] = wd if isinstance(wd, dict) else {"webdriver": None}

        for name, site in SITES.items():
            print(f"  [{name}]...", end=" ", flush=True)
            try:
                await tab.go_to(site["url"])
                await asyncio.sleep(site["wait"])
                data = await evaluate_json(tab, site["js"])
                results[name] = data if data else {"status": "error", "error": "eval None"}
                try:
                    await tab.take_screenshot(path=str(SCREENSHOTS_DIR / f"pydoll_{name}.png"))
                except Exception:
                    pass
                print("OK")
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                print(f"ERROR: {e}")

    results["elapsed_s"] = round(time.time() - t0, 1)
    return results


# ═══════════════════════════════════════════════════════════════════════
# Report
# ═══════════════════════════════════════════════════════════════════════

def print_report(all_results: dict, chrome_path: str) -> None:
    frameworks = list(all_results.keys())
    print("\n" + "=" * 120)
    print("COMPARATIVE DETECTION TEST REPORT")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Chrome: {chrome_path}")
    print("=" * 120)

    # Webdriver
    print("\n--- navigator.webdriver ---")
    for fw in frameworks:
        r = all_results[fw]
        wd = r.get("webdriver_check", {})
        wd_val = wd.get("webdriver", "N/A") if isinstance(wd, dict) else wd
        icon = "PASS" if wd_val is False else "FAIL"
        print(f"  {fw:<26} webdriver={wd_val!s:<8} [{icon}]")

    # Sannysoft
    print("\n--- bot.sannysoft.com ---")
    for fw in frameworks:
        r = all_results[fw].get("sannysoft", {})
        if not isinstance(r, dict):
            print(f"  {fw:<26} ERROR: non-dict result ({type(r).__name__})")
            continue
        if r.get("status") == "error":
            print(f"  {fw:<26} ERROR: {r.get('error', 'unknown')[:60]}")
            continue
        p, f, w = r.get("passed", 0), r.get("failed", 0), r.get("warnings", 0)
        details = r.get("details", {})
        failed_tests = [n for n, d in details.items() if isinstance(d, dict) and d.get("status") == "failed"]
        status = "PASS" if f == 0 else "FAIL"
        print(f"  {fw:<26} passed={p} failed={f} warn={w} [{status}]")
        for ft in failed_tests:
            print(f"  {'':<26}   FAIL: {ft}")

    # CreepJS
    print("\n--- CreepJS ---")
    for fw in frameworks:
        r = all_results[fw].get("creepjs", {})
        if r.get("status") == "error":
            print(f"  {fw:<26} ERROR: {r.get('error', 'unknown')[:60]}")
            continue
        headless = r.get("headless_pct", "?")
        like_headless = r.get("like_headless_pct", "?")
        stealth = r.get("stealth_pct", "?")
        lies = r.get("lies_detected", "?")
        print(f"  {fw:<26} headless={headless}% like_headless={like_headless}% stealth={stealth}% lies={lies}")

    # Canvas
    print("\n--- BrowserLeaks Canvas ---")
    for fw in frameworks:
        r = all_results[fw].get("browserleaks_canvas", {})
        if r.get("status") == "error":
            print(f"  {fw:<26} ERROR: {r.get('error', '')[:60]}")
            continue
        h = r.get("canvasHash") or "N/A"
        u = r.get("uniqueness") or "N/A"
        print(f"  {fw:<26} hash={h[:20]}... uniq={u[:50]}")

    # WebGL
    print("\n--- BrowserLeaks WebGL ---")
    for fw in frameworks:
        r = all_results[fw].get("browserleaks_webgl", {})
        if r.get("status") == "error":
            print(f"  {fw:<26} ERROR")
            continue
        v = r.get("vendor") or "N/A"
        rnd = r.get("renderer") or "N/A"
        print(f"  {fw:<26} vendor={v}")
        print(f"  {'':<26} renderer={rnd[:70]}")

    # BrowserScan
    print("\n--- browserscan.net ---")
    for fw in frameworks:
        r = all_results[fw].get("browserscan", {})
        if r.get("status") == "error":
            print(f"  {fw:<26} ERROR: {r.get('error', '')[:60]}")
            continue
        print(f"  {fw:<26} bot_detected={r.get('bot_detected', 'N/A')} webdriver={r.get('webdriver', 'N/A')}")

    # Summary matrix
    print("\n" + "=" * 120)
    print("SUMMARY MATRIX")
    print("=" * 120)

    col_w = 18
    header = f"{'Test':<22}"
    for fw in frameworks:
        header += f"{fw[:col_w-1]:<{col_w}}"
    print(header)
    print("-" * (22 + col_w * len(frameworks)))

    checks = [
        ("webdriver=false", lambda r: (r.get("webdriver_check", {}) or {}).get("webdriver") is False),
        ("sannysoft 0 fails", lambda r: r.get("sannysoft", {}).get("failed", -1) == 0),
        ("creepjs headless=0%", lambda r: r.get("creepjs", {}).get("headless_pct", -1) == 0),
        ("creepjs stealth=0%", lambda r: r.get("creepjs", {}).get("stealth_pct", -1) == 0),
        ("creepjs lies=0", lambda r: r.get("creepjs", {}).get("lies_detected", -1) == 0),
        ("canvas hash present", lambda r: bool(r.get("browserleaks_canvas", {}).get("canvasHash"))),
        ("webgl vendor present", lambda r: bool(r.get("browserleaks_webgl", {}).get("vendor"))),
        ("browserscan no bot", lambda r: r.get("browserscan", {}).get("bot_detected") is False),
    ]

    score = {fw: 0 for fw in frameworks}
    for check_name, check_fn in checks:
        row = f"{check_name:<22}"
        for fw in frameworks:
            try:
                passed = check_fn(all_results[fw])
            except Exception:
                passed = False
            row += f"{'PASS':<{col_w}}" if passed else f"{'FAIL':<{col_w}}"
            if passed:
                score[fw] += 1
        print(row)

    print("-" * (22 + col_w * len(frameworks)))
    row = f"{'SCORE':<22}"
    for fw in frameworks:
        row += f"{score[fw]}/{len(checks):<{col_w-3}}"
    print(row)

    print(f"{'ELAPSED (s)':<22}", end="")
    for fw in frameworks:
        t = all_results[fw].get("elapsed_s", "?")
        print(f"{t:<{col_w}}", end="")
    print()
    print("=" * 120)


RUNNERS = {
    "tellurium": run_tellurium,
    "selenium": run_selenium,
    "playwright": run_playwright,
    "playwright_stealth": run_playwright_stealth,
    "nodriver": run_nodriver,
    "undetected_chromedriver": run_undetected_chromedriver,
    "drissionpage": run_drissionpage,
    "pydoll": run_pydoll,
}


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Comparative browser detection tests")
    parser.add_argument("--frameworks", type=str, default="all",
                        help="Comma-separated list or 'all'")
    parser.add_argument("--chrome-path", type=str, default=DEFAULT_CHROME,
                        help="Chrome binary path")
    parser.add_argument("--output", type=str, default=str(RESULTS_FILE),
                        help="Output JSON file")
    args = parser.parse_args()

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.frameworks == "all":
        fw_list = list(RUNNERS.keys())
    else:
        fw_list = [f.strip() for f in args.frameworks.split(",")]

    all_results = {}
    for fw_name in fw_list:
        if fw_name not in RUNNERS:
            print(f"Unknown framework: {fw_name}")
            continue
        try:
            result = await RUNNERS[fw_name](args.chrome_path)
            all_results[fw_name] = result
        except Exception as e:
            print(f"\n[{fw_name}] FATAL ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_results[fw_name] = {"framework": fw_name, "status": "fatal_error", "error": str(e)}

    with open(args.output, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nRaw results saved to {args.output}")

    print_report(all_results, args.chrome_path)


if __name__ == "__main__":
    asyncio.run(main())
