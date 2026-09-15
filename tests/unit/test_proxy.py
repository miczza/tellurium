from tellurium.browser.proxy import ProxyForwarder, parse_proxy_url


def test_parse_proxy_url_http():
    result = parse_proxy_url("http://user:pass@proxy.example.com:8080")
    assert result["scheme"] == "http"
    assert result["host"] == "proxy.example.com"
    assert result["port"] == 8080
    assert result["username"] == "user"
    assert result["password"] == "pass"


def test_parse_proxy_url_socks5():
    result = parse_proxy_url("socks5://admin:secret@socks.example.com:1080")
    assert result["scheme"] == "socks5"
    assert result["host"] == "socks.example.com"
    assert result["port"] == 1080
    assert result["username"] == "admin"


def test_parse_proxy_url_no_auth():
    result = parse_proxy_url("http://proxy.example.com:3128")
    assert result["username"] is None
    assert result["password"] is None


def test_parse_proxy_url_default_port():
    result = parse_proxy_url("http://proxy.example.com")
    assert result["port"] == 8080


def test_parse_proxy_url_socks_default_port():
    result = parse_proxy_url("socks5://proxy.example.com")
    assert result["port"] == 1080


async def test_forwarder_starts_on_random_port():
    forwarder = ProxyForwarder("proxy.example.com", 8080, "user", "pass")
    await forwarder.start()
    assert 1024 < forwarder.port < 65536
    await forwarder.stop()


async def test_forwarder_stop_idempotent():
    forwarder = ProxyForwarder("proxy.example.com", 8080, "user", "pass")
    await forwarder.start()
    await forwarder.stop()
    await forwarder.stop()  # should not raise
