import pytest
from tellurium import Browser


async def test_launch_and_close():
    browser = await Browser.launch(headless=True)
    try:
        assert browser is not None
        assert len(browser.tabs) >= 1
    finally:
        await browser.close()


async def test_new_tab(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    title = await tab.eval("document.title")
    assert title == "Basic Test Page"


async def test_context_manager():
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.new_tab("about:blank")
        assert tab is not None
    finally:
        await browser.close()
