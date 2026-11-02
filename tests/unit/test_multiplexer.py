"""Multiplexer options, bind names and token leaks, with no Chrome."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("websockets")

from tellurium import Multiplexer  # noqa: E402
from tellurium.browser.proxy import hide_credentials, parse_proxy_url, redact_proxy_url  # noqa: E402
from tellurium.multiplexer.multiplexer import _url_host  # noqa: E402


@pytest.mark.parametrize("name", ["proxy", "seed", "user_data_dir", "stealth"])
def test_options_the_pool_decides_raise_type_error(name):
    with pytest.raises(TypeError, match=name):
        Multiplexer(2, **{name: None})


def test_unknown_launch_options_raise_type_error():
    with pytest.raises(TypeError, match="nope"):
        Multiplexer(2, nope=1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"size": 0},
        {"size": 2, "warm": 3},
        {"size": 2, "warm": -1},
        {"size": 1, "acquire_timeout": 0},
    ],
)
def test_bad_sizes_raise_value_error(kwargs):
    size = kwargs.pop("size")
    with pytest.raises(ValueError):
        Multiplexer(size, **kwargs)


def test_one_proxy_string_is_refused():
    with pytest.raises(TypeError, match="list"):
        Multiplexer(1, proxies="http://127.0.0.1:8080")


def test_launch_options_are_accepted():
    mux = Multiplexer(2, warm=1, headless=True, browser="stock", geoip=False, args=["--mute-audio"])
    status = mux.status()
    assert status["size"] == 2 and status["slots"] == [] and mux.url is None


def test_without_the_extra_the_error_says_how_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "websockets", None)
    monkeypatch.setitem(sys.modules, "websockets.asyncio", None)
    with pytest.raises(ImportError, match=r"tellurium\[multiplex\]"):
        Multiplexer(1)


def test_proxy_credentials_never_reach_the_status():
    assert redact_proxy_url("http://user:p@ss@127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert redact_proxy_url("socks5://127.0.0.1:1080") == "socks5://127.0.0.1:1080"
    assert redact_proxy_url("alice:pw@h:1/x") == "h:1/x"
    assert redact_proxy_url(None) is None


@pytest.mark.parametrize(
    "url", ["htp://alice:S3cretPW@h:8080", "http://alice:S3cretPW@h:notaport", "ftp://S3cretPW@h"]
)
def test_proxy_parse_errors_do_not_quote_the_password(url):
    with pytest.raises(ValueError) as error:
        parse_proxy_url(url)
    assert "S3cretPW" not in str(error.value) and "alice" not in str(error.value)


def test_credentials_are_masked_in_any_message():
    url = "http://al%69ce:S3cret%2FPW@h:8080"
    text = "failed: http://alice:S3cret/PW@h and al%69ce:S3cret%2FPW"
    masked = hide_credentials(text, url)
    assert "S3cret" not in masked and "alice" not in masked and "al%69ce" not in masked
    assert hide_credentials("nothing", "http://h:1") == "nothing"


@pytest.mark.parametrize(
    ("bind", "url_host"),
    [("0.0.0.0", "127.0.0.1"), ("::", "[::1]"), ("::1", "[::1]"), ("127.0.0.2", "127.0.0.2")],
)
def test_the_url_names_a_reachable_host(bind, url_host):
    assert _url_host(bind) == url_host


SPECIAL = ["S3cret/PW", "S3cret@PW", "S3cret:PW", "S3cret#PW", "S3cret?PW", "S3/c@r:e#t?PW"]


@pytest.mark.parametrize("password", SPECIAL)
def test_a_password_with_url_characters_never_shows(password):
    url = f"http://alice:{password}@127.0.0.1:18084"
    assert redact_proxy_url(url) == "http://127.0.0.1:18084"
    assert "PW" not in hide_credentials(f"could not reach {url} ({password})", url)
    info = parse_proxy_url(url)
    assert (info["username"], info["password"]) == ("alice", password)
    assert (info["host"], info["port"]) == ("127.0.0.1", 18084)
    for bad in (f"htp://alice:{password}@h:1", f"http://alice:{password}@h:port"):
        with pytest.raises(ValueError) as error:
            parse_proxy_url(bad)
        assert "PW" not in str(error.value) and "alice" not in str(error.value)


@pytest.mark.parametrize("password", SPECIAL)
async def test_browser_launch_errors_never_quote_the_password(password):
    from tellurium import Browser

    with pytest.raises(ValueError) as error:
        await Browser.launch(proxy=f"htp://alice:{password}@127.0.0.1:18084")
    assert "PW" not in str(error.value) and "alice" not in str(error.value)


def test_a_password_with_scheme_separator_and_no_scheme_never_shows():
    url = "alice:pa://ss@127.0.0.1:18084"
    info = parse_proxy_url(url)
    assert (info["scheme"], info["username"], info["password"]) == ("http", "alice", "pa://ss")
    assert redact_proxy_url(url) == "127.0.0.1:18084"
    assert "pa:" not in hide_credentials(f"bad {url}", url)
    for bad in ("alice:pa://ss@127.0.0.1:port", "htp://alice:pa://ss@h:1"):
        with pytest.raises(ValueError) as error:
            parse_proxy_url(bad)
        assert "alice" not in str(error.value) and "pa:" not in str(error.value)
