"""Under stealth the advertised UA must match the real Chrome major version."""


async def test_stealth_ua_matches_real_binary_version(local_server):
    from tellurium import Browser

    browser = await Browser.launch(headless=True, stealth=True, seed=1)
    async with browser:
        info = await browser._router.root.send("Browser.getVersion", {})
        real = info["product"].rsplit("/", 1)[1]
        prof = browser._stealth_profile
        assert prof.browser_version == real
        # userAgentData needs a secure context: 127.0.0.1 is potentially trustworthy
        tab = await browser.new_tab(f"{local_server}/basic.html")
        ua = await tab.eval("navigator.userAgent")
        assert f"Chrome/{real}" in ua
        brands = await tab.eval("navigator.userAgentData.brands.map(b => b.version)")
        assert real.split(".")[0] in brands
