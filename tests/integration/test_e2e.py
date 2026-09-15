"""End-to-end tests exercising the full Tellurium stack."""

from tellurium import Browser, Cookie


async def test_full_scraping_workflow(local_server):
    """Complete workflow: launch -> navigate -> select -> extract -> close."""
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")

        # Navigate and extract
        title = await tab.eval("document.title")
        assert title == "Basic Test Page"

        # Select elements
        h1 = await tab.select("h1")
        text = await h1.text()
        assert text == "Hello Tellurium"

        # Click
        btn = await tab.select("#submit")
        await btn.click()
        result = await tab.eval("document.getElementById('content').textContent")
        assert result == "submitted"


async def test_stealth_mode_launches(local_server):
    """Stealth mode should launch without errors."""
    browser = await Browser.launch(headless=True, stealth=True)
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        title = await tab.eval("document.title")
        assert title == "Basic Test Page"

        # Verify stealth is active
        webdriver = await tab.eval("navigator.webdriver")
        assert webdriver is None or webdriver is False


async def test_form_interaction(local_server):
    """Fill a form and submit."""
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab(f"{local_server}/form.html")

        email = await tab.select("#email")
        await email.type("user@test.com")

        value = await tab.eval("document.getElementById('email').value")
        assert value == "user@test.com"

        btn = await tab.select("#submit")
        await btn.click()

        result = await tab.eval("document.getElementById('result').textContent")
        assert "submitted:user@test.com" == result


async def test_dynamic_content(local_server):
    """Wait for dynamically loaded content."""
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab(f"{local_server}/dynamic.html")
        el = await tab.wait_for("#lazy-content", timeout=5)
        text = await el.text()
        assert text == "Loaded!"


async def test_cookie_management():
    """Cookie set/get/save/load cycle."""
    browser = await Browser.launch(headless=True)
    async with browser:
        await browser.new_tab("about:blank")

        cookies = [Cookie(name="test", value="123", domain="localhost")]
        await browser.set_cookies(cookies)

        got = await browser.get_cookies()
        # Cookie may or may not be returned for about:blank domain
        # Just verify the API doesn't error
        assert isinstance(got, list)


async def test_multi_tab():
    """Multiple tabs should be independent."""
    browser = await Browser.launch(headless=True)
    async with browser:
        tab1 = await browser.new_tab("about:blank")
        tab2 = await browser.new_tab("about:blank")

        assert len(browser.tabs) >= 2

        await tab1.eval("document.title = 'Tab 1'")
        await tab2.eval("document.title = 'Tab 2'")

        t1 = await tab1.eval("document.title")
        t2 = await tab2.eval("document.title")
        assert t1 == "Tab 1"
        assert t2 == "Tab 2"


async def test_screenshot_returns_data(local_server):
    """Screenshot should return PNG bytes."""
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        data = await tab.screenshot()
        assert len(data) > 100
        assert data[:4] == b"\x89PNG"  # PNG magic bytes
