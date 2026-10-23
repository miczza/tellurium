import asyncio

import pytest

from tellurium.browser.proxy import (
    ProxyForwarder,
    forwarder_for,
    parse_proxy_url,
    proxy_server_flag,
)


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


# --- audit M7: the scheme reaches Chrome ------------------------------------


@pytest.mark.parametrize(
    ("url", "flag"),
    [
        ("socks5://10.0.0.1:1080", "socks5://10.0.0.1:1080"),
        ("socks4://10.0.0.1", "socks4://10.0.0.1:1080"),
        ("https://10.0.0.1:8443", "https://10.0.0.1:8443"),
        ("http://proxy.example.com:3128", "http://proxy.example.com:3128"),
        ("proxy.example.com:3128", "http://proxy.example.com:3128"),
        ("http://[::1]:3128", "http://[::1]:3128"),
        ("socks5://[2001:db8::2]:9050", "socks5://[2001:db8::2]:9050"),
    ],
)
def test_proxy_server_flag_keeps_the_scheme(url, flag):
    assert proxy_server_flag(url) == flag


def test_proxy_server_flag_rejects_unknown_scheme():
    with pytest.raises(ValueError, match="ftp"):
        proxy_server_flag("ftp://10.0.0.1:21")


def test_socks_with_credentials_is_refused():
    with pytest.raises(ValueError, match="SOCKS"):
        forwarder_for("socks5://user:pw@10.0.0.1:1080")


def test_forwarder_only_for_credentials():
    assert forwarder_for("http://10.0.0.1:3128") is None
    assert forwarder_for("socks5://10.0.0.1:1080") is None
    forwarder = forwarder_for("https://us%40er:p%3Aw@10.0.0.1:8443")
    assert forwarder is not None
    assert forwarder._username == "us@er" and forwarder._password == "p:w"
    assert forwarder._tls is True
    assert forwarder_for("http://u:p@10.0.0.1:3128")._tls is False


def test_launch_rejects_socks_credentials_before_spawning(monkeypatch):
    from tellurium.browser.browser import Browser
    from tellurium.browser.process import BrowserProcess

    async def no_spawn(*a, **kw):
        raise AssertionError("Chrome must not be started")

    monkeypatch.setattr(BrowserProcess, "spawn", no_spawn)
    with pytest.raises(ValueError, match="SOCKS"):
        asyncio.run(Browser.launch(executable="/bin/false", proxy="socks5://user:pw@10.0.0.1:1080"))
