"""The HTTP guard of ``tellurium mcp --http``: the token file, the Bearer
check, Origin and Host, without a server."""

from __future__ import annotations

import os
import re
import stat
import threading

import pytest

pytest.importorskip("mcp")

from tellurium.mcp import auth  # noqa: E402

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")


# -- token file ----------------------------------------------------------


@posix_only
def test_token_is_created_once_with_0600_and_reused(tmp_path):
    path = tmp_path / "home" / "mcp-token"
    token = auth.load_or_create_token(path)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", token)  # 32 random bytes, base64url
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert auth.load_or_create_token(path) == token
    assert [p.name for p in path.parent.iterdir()] == ["mcp-token"]  # no temp file left


@posix_only
def test_token_creation_ignores_a_loose_umask(tmp_path):
    old = os.umask(0)
    try:
        path = tmp_path / "mcp-token"
        auth.load_or_create_token(path)
    finally:
        os.umask(old)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@posix_only
@pytest.mark.parametrize("mode", [0o644, 0o640, 0o604, 0o660])
def test_token_file_readable_by_others_is_refused(tmp_path, mode):
    path = tmp_path / "mcp-token"
    auth.load_or_create_token(path)
    path.chmod(mode)
    with pytest.raises(auth.TokenFileError, match="chmod 600"):
        auth.load_or_create_token(path)


@posix_only
def test_token_file_that_is_a_symlink_is_refused(tmp_path):
    real = tmp_path / "elsewhere"
    auth.load_or_create_token(real)
    link = tmp_path / "mcp-token"
    link.symlink_to(real)
    with pytest.raises(auth.TokenFileError, match="regular file"):
        auth.load_or_create_token(link)


@posix_only
@pytest.mark.parametrize("content", ["", "short", "has spaces in it and is long enough!!"])
def test_token_file_with_a_bad_token_is_refused(tmp_path, content):
    path = tmp_path / "mcp-token"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    os.write(fd, content.encode())
    os.close(fd)
    with pytest.raises(auth.TokenFileError, match="base64url"):
        auth.load_or_create_token(path)


@posix_only
def test_concurrent_creators_agree_on_one_token(tmp_path):
    path = tmp_path / "mcp-token"
    got: list[str] = []
    threads = [
        threading.Thread(target=lambda: got.append(auth.load_or_create_token(path)))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(got) == 8 and len(set(got)) == 1


# -- request checks --------------------------------------------------------

TOKEN = "A" * 43


def _scope(headers: dict[str, str] | None = None, query: str = "", path: str = "/mcp"):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return {"type": "http", "path": path, "query_string": query.encode(), "headers": raw}


def _guard(**kw) -> auth.Guard:
    return auth.Guard(
        token=TOKEN,
        hosts=kw.pop("hosts", auth.allowed_hosts("127.0.0.1")),
        port=kw.pop("port", 8765),
    )


_OK = {"Host": "127.0.0.1:8765", "Authorization": f"Bearer {TOKEN}"}


def test_good_request_passes():
    assert _guard().check(_scope(_OK)) is None


def test_bearer_scheme_is_case_insensitive():
    assert _guard().check(_scope({**_OK, "Authorization": f"bearer {TOKEN}"})) is None


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        f"Basic {TOKEN}",
        "Bearer",
        "Bearer wrong",
        f"Bearer {TOKEN}x",
        f"Bearer {TOKEN[:-1]}",
    ],
)
def test_missing_or_wrong_token_is_401(authorization):
    headers = {"Host": "127.0.0.1:8765"}
    if authorization is not None:
        headers["Authorization"] = authorization
    refused = _guard().check(_scope(headers))
    assert refused is not None and refused.status == 401
    assert (b"www-authenticate", b"Bearer") in refused.headers


@pytest.mark.parametrize(
    "query", [f"token={TOKEN}", f"access_token={TOKEN}", f"x=1&Authorization=Bearer%20{TOKEN}"]
)
def test_token_in_the_url_is_refused_even_with_the_header(query):
    refused = _guard().check(_scope(_OK, query=query))
    assert refused is not None and refused.status == 400
    assert "Authorization header" in refused.message


def test_token_value_anywhere_in_the_url_is_refused():
    refused = _guard().check(_scope(_OK, query=f"q={TOKEN}"))
    assert refused is not None and refused.status == 400


def test_token_compared_in_constant_time(monkeypatch):
    seen = []
    real = auth.hmac.compare_digest
    monkeypatch.setattr(auth.hmac, "compare_digest", lambda a, b: seen.append(1) or real(a, b))
    _guard().check(_scope(_OK))
    assert seen


@pytest.mark.parametrize(
    "origin", ["https://evil.example", "null", "http://127.0.0.1:8765", "http://localhost:8765"]
)
def test_any_origin_is_403_even_with_the_token(origin):
    """MCP clients are not web pages: whatever a browser sends is refused,
    the server's own address included."""
    refused = _guard().check(_scope({**_OK, "Origin": origin}))
    assert refused is not None and refused.status == 403


def test_origin_checked_before_the_token():
    refused = _guard().check(_scope({"Host": "127.0.0.1:8765", "Origin": "https://evil.example"}))
    assert refused is not None and refused.status == 403


@pytest.mark.parametrize(
    "host", ["evil.example:8765", "127.0.0.1:9999", "127.0.0.1", "attacker.localhost:8765", ""]
)
def test_foreign_host_is_403(host):
    headers = {**_OK, "Host": host} if host else {"Authorization": _OK["Authorization"]}
    refused = _guard().check(_scope(headers))
    assert refused is not None and refused.status == 403


@pytest.mark.parametrize("host", ["localhost:8765", "LOCALHOST:8765", "[::1]:8765"])
def test_loopback_names_pass_on_a_loopback_bind(host):
    assert _guard().check(_scope({**_OK, "Host": host})) is None


def test_specific_bind_accepts_only_its_own_host():
    guard = _guard(hosts=auth.allowed_hosts("192.168.1.5"))
    assert guard.check(_scope({**_OK, "Host": "192.168.1.5:8765"})) is None
    refused = guard.check(_scope({**_OK, "Host": "localhost:8765"}))
    assert refused is not None and refused.status == 403


def test_wildcard_bind_does_not_check_host():
    assert auth.allowed_hosts("0.0.0.0") is None
    guard = _guard(hosts=None)
    assert guard.check(_scope({**_OK, "Host": "whatever:8765"})) is None


def test_other_paths_are_404_after_the_checks():
    refused = _guard().check(_scope(_OK, path="/other"))
    assert refused is not None and refused.status == 404
    unauth = _guard().check(_scope({"Host": "127.0.0.1:8765"}, path="/other"))
    assert unauth is not None and unauth.status == 401


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("127.0.0.2", True),
        ("::1", True),
        ("localhost", True),
        ("0.0.0.0", False),
        ("192.168.1.5", False),
        ("example.com", False),
    ],
)
def test_is_loopback(host, loopback):
    assert auth.is_loopback(host) is loopback


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("127.0.0.1:8765", ("127.0.0.1", 8765)),
        ("localhost:0", ("localhost", 0)),
        ("[::1]:8765", ("::1", 8765)),
        (":8765", ("127.0.0.1", 8765)),
    ],
)
def test_parse_bind(text, expected):
    assert auth.parse_bind(text) == expected


@pytest.mark.parametrize("text", ["127.0.0.1", "host:port", "127.0.0.1:70000", "[::1"])
def test_parse_bind_rejects_garbage(text):
    with pytest.raises(ValueError):
        auth.parse_bind(text)


@pytest.mark.parametrize(
    "name", ["Mcp-Session-Id", "Authorization", "Host", "Origin", "Mcp-Protocol-Version"]
)
def test_a_repeated_header_that_decides_access_or_identity_is_400(name):
    scope = _scope(_OK)
    value = {"Mcp-Session-Id": "a", "Origin": "x", "Mcp-Protocol-Version": "2025-11-25"}.get(
        name, _OK.get(name, "")
    )
    scope["headers"] += [(name.lower().encode(), value.encode())] * 2
    refused = _guard().check(scope)
    assert refused is not None and refused.status == 400
    assert name.lower() in refused.message.lower()


@posix_only
@pytest.mark.parametrize("mode", [0o777, 0o775, 0o757])
def test_home_writable_by_others_is_refused(tmp_path, mode):
    home = tmp_path / "home"
    home.mkdir()
    home.chmod(mode)
    with pytest.raises(auth.TokenFileError, match="writable by other users"):
        auth.load_or_create_token(home / "mcp-token")
    assert not (home / "mcp-token").exists()


@posix_only
def test_home_or_token_of_another_user_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "home" / "mcp-token"
    auth.load_or_create_token(path)
    monkeypatch.setattr(auth.os, "getuid", lambda: os.stat(path).st_uid + 1)
    with pytest.raises(auth.TokenFileError, match="another user"):
        auth.load_or_create_token(path)


@posix_only
def test_token_swapped_for_a_symlink_after_the_checks_is_not_read(tmp_path, monkeypatch):
    """The checks run on the descriptor that is read: swapping the file for a
    symlink after them changes nothing."""
    path = tmp_path / "mcp-token"
    token = auth.load_or_create_token(path)
    evil = tmp_path / "evil"
    fd = os.open(evil, os.O_WRONLY | os.O_CREAT, 0o600)
    os.write(fd, b"E" * 43)
    os.close(fd)
    calls = {"lstat": 0}

    def swap():
        if not path.is_symlink():
            path.unlink()
            path.symlink_to(evil)

    real_lstat, real_fstat = os.lstat, os.fstat

    def lstat(p, *a, **kw):
        info = real_lstat(p, *a, **kw)
        if str(p) == str(path):
            calls["lstat"] += 1
            if calls["lstat"] == 2:  # the check before reading, if any
                swap()
        return info

    def fstat(fd):
        info = real_fstat(fd)
        swap()
        return info

    monkeypatch.setattr(auth.os, "lstat", lstat)
    monkeypatch.setattr(auth.os, "fstat", fstat)
    assert auth.load_or_create_token(path) == token


@posix_only
def test_token_that_is_a_fifo_is_refused_without_blocking(tmp_path):
    path = tmp_path / "mcp-token"
    os.mkfifo(path, 0o600)
    with pytest.raises(auth.TokenFileError, match="regular file"):
        auth.load_or_create_token(path)
