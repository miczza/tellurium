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
