async def test_navigate(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    title = await tab.eval("document.title")
    assert title == "Basic Test Page"


async def test_select_element(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    el = await tab.select("#submit")
    tag = await el.tag()
    assert tag == "button"


async def test_find_by_text(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    el = await tab.find("Submit")
    assert el is not None
    tag = await el.tag()
    assert tag == "button"


async def test_eval(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    title = await tab.eval("document.title")
    assert isinstance(title, str)
    assert "Basic" in title


async def test_wait_for(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/dynamic.html")
    el = await tab.wait_for("#lazy-content", timeout=5)
    text = await el.text()
    assert text == "Loaded!"


async def test_screenshot(browser, local_server, tmp_path):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    data = await tab.screenshot()
    assert len(data) > 100
