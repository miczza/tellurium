import pytest
from tellurium import Browser

pytestmark = pytest.mark.stealth


async def test_webdriver_undefined():
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("navigator.webdriver")
        assert result is None or result is False


async def test_chrome_runtime_exists():
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        result = await tab.eval("typeof window.chrome")
        assert result == "object"


async def test_plugins_not_empty():
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("about:blank")
        count = await tab.eval("navigator.plugins.length")
        assert count > 0


async def test_hardware_concurrency_spoofed():
    async with await Browser.launch(headless=True, stealth=True, seed=42069) as browser:
        tab = await browser.new_tab("about:blank")
        hc = await tab.eval("navigator.hardwareConcurrency")
        # Should be one of the profile values, not necessarily the real one
        assert hc in [4, 8, 12, 16]


async def test_webgl_renderer_spoofed():
    async with await Browser.launch(headless=True, stealth=True, seed=42069) as browser:
        tab = await browser.new_tab("about:blank")
        renderer = await tab.eval("""
            (() => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl');
                if (!gl) return null;
                const ext = gl.getExtension('WEBGL_debug_renderer_info');
                if (!ext) return null;
                return gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
            })()
        """)
        # Should be a spoofed renderer from our GPU database, not the real one
        assert renderer is not None
        assert "ANGLE" in renderer


async def test_seed_determinism():
    """Same seed should produce same navigator properties."""
    results = []
    for _ in range(2):
        async with await Browser.launch(headless=True, stealth=True, seed=42069) as browser:
            tab = await browser.new_tab("about:blank")
            hc = await tab.eval("navigator.hardwareConcurrency")
            results.append(hc)
    assert results[0] == results[1]


async def test_sannysoft_no_critical_fails():
    """Navigate to bot.sannysoft.com and check for critical failures."""
    async with await Browser.launch(headless=True, stealth=True) as browser:
        tab = await browser.new_tab("https://bot.sannysoft.com/")
        await tab.wait(3)
        results = await tab.eval("""
            Array.from(document.querySelectorAll('tr')).map(r => ({
                test: r.cells[0]?.textContent?.trim(),
                result: r.cells[1]?.textContent?.trim()
            })).filter(r => r.test && r.result)
        """)
        if results:
            # Check critical tests
            critical_tests = ["User Agent", "WebDriver", "Chrome"]
            for r in results:
                if r["test"] in critical_tests:
                    assert r["result"] != "FAIL", f"Critical test failed: {r['test']}"
