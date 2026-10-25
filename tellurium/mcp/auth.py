"""Who may talk to ``tellurium mcp --http``: the token file, and the checks every
HTTP request passes before it reaches MCP.

The token is required on loopback too (any local process, or a web page via DNS
rebinding, can reach a loopback port), only in the ``Authorization: Bearer``
header (URLs end up in logs), and compared in constant time. A browser always
sends ``Origin`` on the requests a page makes: absent means a non-browser
client, otherwise it must be in the allowlist. ``Host`` must name the address
the server is bound to, which defeats DNS rebinding even before the token.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

TOKEN_BYTES = 32
ENDPOINT = "/mcp"
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,}")
_URL_TOKEN_KEYS = {"token", "access_token", "authorization", "auth", "bearer"}
_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "[::1]"})
_WILDCARDS = {"0.0.0.0", "::", ""}
# Headers sent at most once: they decide access, the client or the protocol.
_SINGLE_HEADERS = frozenset(
    {b"host", b"origin", b"authorization", b"mcp-session-id", b"mcp-protocol-version"}
)


class TokenFileError(Exception):
    """The token file exists but cannot be trusted or used."""


def load_or_create_token(path: Path) -> str:
    """The token in *path*, created (32 random bytes, base64url, mode 0600) when
    missing. A file others can read, a symlink or a malformed token is refused.
    Blocking: call it through ``asyncio.to_thread``."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not os.path.lexists(path):
        _create(path, secrets.token_urlsafe(TOKEN_BYTES))
    return _read(path)


def _create(path: Path, token: str) -> None:
    """Write *token* to a private temp file, then link it into place: readers
    never see a partial file, and of two racing servers the first one wins."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            os.write(fd, f"{token}\n".encode("ascii"))
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass  # someone else created it first: theirs is the token
    finally:
        tmp.unlink(missing_ok=True)


def _read(path: Path) -> str:
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise TokenFileError(f"{path} is not a regular file: remove it to get a new token")
    if os.name == "posix":
        if info.st_mode & 0o077:
            raise TokenFileError(
                f"{path} is readable by other users (mode {stat.S_IMODE(info.st_mode):04o}): "
                f"chmod 600 {path}, or delete it for a new token"
            )
        if info.st_uid != os.getuid():
            raise TokenFileError(f"{path} belongs to another user: delete it for a new token")
    token = path.read_text(encoding="ascii", errors="replace").strip()
    if not _TOKEN.fullmatch(token):
        raise TokenFileError(
            f"{path} does not hold a token (32+ base64url characters): delete it for a new one"
        )
    return token


# --------------------------------------------------------------------------- #
# Addresses
# --------------------------------------------------------------------------- #


def parse_bind(text: str) -> tuple[str, int]:
    """``HOST:PORT`` (``[::1]:8765``; empty host = 127.0.0.1) as ``(host, port)``."""
    host, sep, port = text.rpartition(":")
    if not sep or not port.isdigit() or not 0 <= int(port) <= 65535:
        raise ValueError(f"expected HOST:PORT, got {text!r}")
    if host.startswith("[") != host.endswith("]"):
        raise ValueError(f"unbalanced brackets in {text!r}")
    host = host.strip("[]") or "127.0.0.1"
    return host, int(port)


def is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def allowed_hosts(bind_host: str) -> frozenset[str] | None:
    """The ``Host`` names a request may carry for a server bound to *bind_host*:
    the loopback names on loopback, else that address only. ``None`` (no
    check) for a wildcard bind, whose own name the server cannot know."""
    if bind_host in _WILDCARDS:
        return None
    if is_loopback(bind_host):
        return _LOOPBACK_NAMES
    return frozenset({_host_name(bind_host)})


def _host_name(host: str) -> str:
    host = host.lower()
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


def normalize_origins(origins: list[str]) -> frozenset[str]:
    """``scheme://host[:port]`` values, lowercased and without a trailing slash."""
    out = set()
    for origin in origins:
        value = origin.strip().rstrip("/").lower()
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.netloc or parts.path:
            raise ValueError(f"not an origin (scheme://host[:port]): {origin!r}")
        out.add(value)
    return frozenset(out)


# --------------------------------------------------------------------------- #
# Request checks
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Refusal:
    status: int
    message: str
    headers: tuple[tuple[bytes, bytes], ...] = ()


@dataclass(frozen=True)
class Guard:
    """The checks for a server bound to port *port*: *hosts* from
    :func:`allowed_hosts`, *origins* from :func:`normalize_origins`."""

    token: str
    hosts: frozenset[str] | None
    port: int
    origins: frozenset[str]

    def check(self, scope: dict[str, Any]) -> Refusal | None:
        """``None`` when the HTTP request *scope* may reach MCP, else why not.
        Order: repeated headers, Host and Origin (a page must learn nothing),
        the URL, the token, the path."""
        repeated = _repeated(scope)
        if repeated:
            return Refusal(400, f"Header {repeated} sent more than once")
        headers = _headers(scope)
        if not self._host_ok(headers.get("host", "")):
            return Refusal(403, "Host not allowed (this server answers only on its bind address)")
        origin = headers.get("origin")
        if origin is not None and origin.rstrip("/").lower() not in self.origins:
            return Refusal(403, "Origin not allowed: start the server with --allow-origin")
        if self._token_in_url(scope.get("query_string", b"")):
            return Refusal(
                400, "Never put the token in the URL: send it in the Authorization header"
            )
        if not self._token_ok(headers.get("authorization", "")):
            return Refusal(
                401,
                "Missing or wrong token: send 'Authorization: Bearer <token>' "
                "(the token is in the mcp-token file of the server's home)",
                ((b"www-authenticate", b"Bearer"),),
            )
        if scope.get("path") != ENDPOINT:
            return Refusal(404, f"Not found: the MCP endpoint is {ENDPOINT}")
        return None

    def _host_ok(self, host: str) -> bool:
        if self.hosts is None:
            return True
        name, sep, port = host.lower().rpartition(":")
        if not sep or "]" in port:  # no port: only the default one would match
            name, port = host.lower(), ""
        wanted = str(self.port) if self.port != 80 else ""
        return name in self.hosts and port in {wanted, str(self.port)}

    def _token_in_url(self, query: bytes) -> bool:
        text = query.decode("latin-1")
        if not text:
            return False
        if self.token in unquote(text):
            return True
        return any(key.lower() in _URL_TOKEN_KEYS for key, _ in parse_qsl(text, True))

    def _token_ok(self, authorization: str) -> bool:
        scheme, _, given = authorization.strip().partition(" ")
        if scheme.lower() != "bearer":
            return False
        # Constant time over equal-length inputs: no timing tells how much matched.
        return hmac.compare_digest(given.strip().encode(), self.token.encode())


def _repeated(scope: dict[str, Any]) -> str | None:
    """A header that decides access or identity, if it is sent twice: whoever
    reads the first and whoever reads the last would disagree."""
    seen: set[bytes] = set()
    for key, _ in scope.get("headers", []):
        key = key.lower()
        if key in _SINGLE_HEADERS:
            if key in seen:
                return key.decode("latin-1")
            seen.add(key)
    return None


def _headers(scope: dict[str, Any]) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
