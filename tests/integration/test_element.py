async def test_click(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    btn = await tab.select("#submit")
    await btn.click()
    result = await tab.eval("document.getElementById('content').textContent")
    assert result == "submitted"


async def test_type(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/form.html")
    inp = await tab.select("#email")
    await inp.type("test@example.com")
    value = await tab.eval("document.getElementById('email').value")
    assert value == "test@example.com"


async def test_element_text(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    el = await tab.select("h1")
    text = await el.text()
    assert text == "Hello Tellurium"


async def test_element_attributes(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    el = await tab.select("#link")
    href = await el.attr("href")
    assert href == "#clicked"


async def test_element_visibility(browser, local_server):
    tab = await browser.new_tab(f"{local_server}/basic.html")
    el = await tab.select("#submit")
    assert await el.is_visible()
    assert await el.is_enabled()
