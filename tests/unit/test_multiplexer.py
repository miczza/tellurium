"""Multiplexer options, bind names and token leaks, with no Chrome."""

from __future__ import annotations

import sys
from urllib.parse import quote

import pytest

pytest.importorskip("websockets")

from tellurium import Multiplexer  # noqa: E402
from tellurium.multiplexer.multiplexer import _url_host  # noqa: E402
from tellurium.multiplexer.place import _public  # noqa: E402
from tellurium.multiplexer.server import host_names, token_leaked  # noqa: E402

TOKEN = "A" * 20 + "b-_" + "9" * 20


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


@pytest.mark.parametrize("bind", ["0", "0.0.0.0", "::", "::0", "[::]", ""])
def test_every_wildcard_spelling_checks_no_host(bind):
    assert host_names(bind) is None


def test_a_loopback_bind_accepts_its_own_name_and_the_loopback_names():
    names = host_names("127.0.0.2")
    assert {"127.0.0.2", "127.0.0.1", "localhost", "[::1]"} <= names
    assert "[::1]" in host_names("::1")
    assert host_names("192.168.1.5") == frozenset({"192.168.1.5"})
    assert host_names("127.1") >= {"127.0.0.1"}


@pytest.mark.parametrize(
    "target",
    [
        f"/devtools/browser/{TOKEN}",
        f"/devtools/browser/{quote(TOKEN, safe='')}",
        "/devtools/browser/" + quote(quote(TOKEN, safe=""), safe=""),
        "/devtools/browser/" + "".join(f"%{ord(c):02X}" for c in TOKEN),
        f"/json/version?x={TOKEN}",
        "/json/version?token=abc",
        "/json/version?" + quote(quote(f"t={TOKEN}", safe=""), safe=""),
    ],
)
def test_the_token_is_seen_anywhere_in_the_target(target):
    assert token_leaked(target, TOKEN)


@pytest.mark.parametrize("target", ["/devtools/browser/abc", "/json/version", "/json/version/?a=1"])
def test_clean_targets_pass(target):
    assert not token_leaked(target, TOKEN)


def test_proxy_credentials_never_reach_the_status():
    assert _public("http://user:p@ss@127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert _public("socks5://127.0.0.1:1080") == "socks5://127.0.0.1:1080"
    assert _public(None) is None


@pytest.mark.parametrize(
    ("bind", "url_host"),
    [("0.0.0.0", "127.0.0.1"), ("::", "[::1]"), ("::1", "[::1]"), ("127.0.0.2", "127.0.0.2")],
)
def test_the_url_names_a_reachable_host(bind, url_host):
    assert _url_host(bind) == url_host
