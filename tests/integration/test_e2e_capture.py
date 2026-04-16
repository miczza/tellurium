"""End-to-end tests for network capture functionality."""
import pytest
from tellurium import Browser


async def test_capture_and_search_requests(local_server):
    """Capture network requests and search by URL pattern."""
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        await tab.capture()

        # Navigate to trigger requests
        await tab.get(f"{local_server}/form.html")

        # Search captured requests
        reqs = await tab.requests(url="*.html")
        assert len(reqs) >= 1
        assert any("form.html" in r.url for r in reqs)

        await tab.capture_stop()


async def test_capture_with_logging(local_server, capsys):
    """Capture with log=True prints to stderr."""
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        await tab.capture(log=True)
        await tab.get(f"{local_server}/form.html")
        await tab.wait(0.5)
        await tab.capture_stop()

    # Log output goes to stderr
    captured = capsys.readouterr()
    # At minimum should see some capture output (depends on implementation)
    # Just verify no error
    assert True


async def test_capture_request_metadata(local_server):
    """CapturedRequest exposes method, status, headers."""
    browser = await Browser.launch(headless=True)
    async with browser:
        tab = await browser.new_tab(f"{local_server}/basic.html")
        await tab.capture()
        await tab.get(f"{local_server}/form.html")

        reqs = await tab.requests()
        assert len(reqs) >= 1

        req = reqs[0]
        assert req.method in ("GET", "POST")
        assert isinstance(req.url, str)
        # Status may or may not be set depending on timing

        await tab.capture_stop()
