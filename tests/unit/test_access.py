"""Access to a local tellurium server, without ASGI: the token file, the bind
address and the checks on headers already lowercased."""

from __future__ import annotations

import os
import stat
from urllib.parse import quote

import pytest

from tellurium import access

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
TOKEN = "A" * 43


# -- token file ----------------------------------------------------------


@posix_only
def test_token_file_name_is_the_callers(tmp_path):
    """The name of the file is an argument: two servers, two tokens."""
    home = tmp_path / "home"
    one = access.load_or_create_token(home / "mcp-token")
    two = access.load_or_create_token(home / "multiplex-token")
    assert one != two
    assert stat.S_IMODE(os.stat(home / "multiplex-token").st_mode) == 0o600
    assert access.load_or_create_token(home / "multiplex-token") == two


@posix_only
def test_token_readable_by_others_is_refused(tmp_path):
    path = tmp_path / "multiplex-token"
    access.load_or_create_token(path)
    path.chmod(0o644)
    with pytest.raises(access.TokenFileError, match="chmod 600"):
        access.load_or_create_token(path)


def test_token_error_is_the_same_class_for_mcp():
    pytest.importorskip("mcp")
    from tellurium.mcp import auth

    assert auth.TokenFileError is access.TokenFileError
    assert auth.load_or_create_token is access.load_or_create_token


# -- addresses -----------------------------------------------------------


def test_bind_and_loopback():
    assert access.parse_bind("127.0.0.1:9339") == ("127.0.0.1", 9339)
    assert access.parse_bind(":9339") == ("127.0.0.1", 9339)
    assert access.parse_bind("[::1]:9339") == ("::1", 9339)
    assert access.is_loopback("::1") and not access.is_loopback("192.168.1.5")
    assert access.allowed_hosts("::1") == frozenset({"localhost", "127.0.0.1", "[::1]"})
    assert access.allowed_hosts("fe80::1") == frozenset({"[fe80::1]"})
    assert access.allowed_hosts("0.0.0.0") is None


# -- header checks -------------------------------------------------------


LOOPBACK = access.allowed_hosts("127.0.0.1")


@pytest.mark.parametrize(
    ("host", "ok"),
    [
        ("127.0.0.1:9339", True),
        ("LOCALHOST:9339", True),
        ("[::1]:9339", True),
        ("127.0.0.1", False),
        ("127.0.0.1:9222", False),
        ("evil.example:9339", False),
        ("", False),
    ],
)
def test_host_ok(host, ok):
    headers = {"host": host} if host else {}
    assert access.host_ok(headers, LOOPBACK, 9339) is ok


def test_host_without_port_passes_on_port_80():
    assert access.host_ok({"host": "localhost"}, LOOPBACK, 80)


def test_wildcard_bind_accepts_any_host():
    assert access.host_ok({"host": "whatever:1"}, None, 9339)


@pytest.mark.parametrize(
    ("query", "inside"),
    [
        ("", False),
        ("session=github", False),
        (f"token={TOKEN}", True),
        ("Access_Token=x", True),
        (f"q=%41{TOKEN[1:]}", True),  # the value, percent-encoded
        (f"x=1&Authorization=Bearer%20{TOKEN}", True),
    ],
)
def test_token_in_url(query, inside):
    assert access.token_in_url(query, TOKEN) is inside


@pytest.mark.parametrize(
    ("authorization", "ok"),
    [
        (f"Bearer {TOKEN}", True),
        (f"bearer {TOKEN}", True),
        (f"  Bearer   {TOKEN}  ", True),
        (None, False),
        ("", False),
        ("Bearer", False),
        (f"Basic {TOKEN}", False),
        (f"Bearer {TOKEN}x", False),
        (f"Bearer {TOKEN[:-1]}", False),
    ],
)
def test_bearer_ok(authorization, ok):
    headers = {} if authorization is None else {"authorization": authorization}
    assert access.bearer_ok(headers, TOKEN) is ok


def test_bearer_compared_in_constant_time(monkeypatch):
    seen = []
    real = access.hmac.compare_digest
    monkeypatch.setattr(access.hmac, "compare_digest", lambda a, b: seen.append(1) or real(a, b))
    assert access.bearer_ok({"authorization": f"Bearer {TOKEN}"}, TOKEN)
    assert seen


def test_repeated_header():
    names = ["Host", "authorization", "Accept", "accept", "AUTHORIZATION"]
    assert access.repeated_header(names) == "authorization"
    assert access.repeated_header(["host", "origin", "accept", "accept"]) is None
    assert access.repeated_header(["x-a", "X-A"], extra={"x-a"}) == "x-a"
    assert {"host", "origin", "authorization"} <= access.SINGLE_HEADERS


LEAKED = "A" * 20 + "b-_" + "9" * 20


@pytest.mark.parametrize("bind", ["0", "0.0.0.0", "::", "::0", "[::]", ""])
def test_every_wildcard_spelling_checks_no_host(bind):
    assert access.allowed_hosts(bind) is None


def test_a_loopback_bind_accepts_its_own_name_and_the_loopback_names():
    names = access.allowed_hosts("127.0.0.2")
    assert {"127.0.0.2", "127.0.0.1", "localhost", "[::1]"} <= names
    assert "[::1]" in access.allowed_hosts("::1")
    assert access.allowed_hosts("192.168.1.5") == frozenset({"192.168.1.5"})
    assert access.allowed_hosts("127.1") >= {"127.0.0.1"}


@pytest.mark.parametrize(
    "target",
    [
        f"/devtools/browser/{LEAKED}",
        f"/devtools/browser/{quote(LEAKED, safe='')}",
        "/devtools/browser/" + quote(quote(LEAKED, safe=""), safe=""),
        "/devtools/browser/" + "".join(f"%{ord(c):02X}" for c in LEAKED),
        f"/json/version?x={LEAKED}",
        "/json/version?token=abc",
        "/json/version?" + quote(quote(f"t={LEAKED}", safe=""), safe=""),
    ],
)
def test_the_token_is_seen_anywhere_in_the_target(target):
    assert access.token_leaked(target, LEAKED)


@pytest.mark.parametrize("target", ["/devtools/browser/abc", "/json/version", "/json/version/?a=1"])
def test_clean_targets_pass(target):
    assert not access.token_leaked(target, LEAKED)
