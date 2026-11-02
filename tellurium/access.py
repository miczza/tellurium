"""Who may talk to a local tellurium server: the token file, the bind address,
and the checks on the headers of every request, with no web framework.

The token is required on loopback too (any local process, or a web page via
DNS rebinding, can reach a loopback port), only in the ``Authorization:
Bearer`` header (URLs end up in logs), and compared in constant time. ``Host``
must name the address the server is bound to, which defeats DNS rebinding
even before the token. The checks read a dict of headers whose names are
already lowercased; what a refusal says and in which order the checks run is
up to each server.
"""

from __future__ import annotations

import errno
import hmac
import ipaddress
import os
import re
import secrets
import socket
import stat
from collections.abc import Iterable, Mapping
from pathlib import Path
from urllib.parse import parse_qsl, unquote

TOKEN_BYTES = 32
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,}")
_URL_TOKEN_KEYS = {"token", "access_token", "authorization", "auth", "bearer"}
_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "[::1]"})
_WILDCARDS = {"0.0.0.0", "::", ""}
#: Headers sent at most once by any client: they decide access.
SINGLE_HEADERS = frozenset({"host", "origin", "authorization"})


# --------------------------------------------------------------------------- #
# Token file
# --------------------------------------------------------------------------- #


class TokenFileError(Exception):
    """The token file exists but cannot be trusted or used."""


def load_or_create_token(path: Path) -> str:
    """The token in *path*, created (32 random bytes, base64url, mode 0600) when
    missing. A folder other users can write to (they could plant their own
    token), a file they can read, a symlink or a malformed token is refused.
    Blocking: call it through ``asyncio.to_thread``."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _check_home(path.parent)
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


def _check_home(home: Path) -> None:
    if os.name != "posix":
        return
    info = os.stat(home)
    if info.st_uid != os.getuid():
        raise TokenFileError(f"{home} belongs to another user: use a folder of yours")
    if info.st_mode & 0o022:
        raise TokenFileError(
            f"{home} is writable by other users (mode {stat.S_IMODE(info.st_mode):04o}): "
            f"chmod go-w {home}"
        )


def _read(path: Path) -> str:
    """The token, with every check made on the descriptor that is read: the
    file cannot be swapped between the checks and the read."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:  # O_NOFOLLOW met a symlink
            raise TokenFileError(
                f"{path} is not a regular file: remove it to get a new token"
            ) from None
        raise
    try:
        info = os.fstat(fd)
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
        raw = os.read(fd, 4096)
    finally:
        os.close(fd)
    token = raw.decode("ascii", errors="replace").strip()
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
    the loopback names (and the address's own) on loopback, else that address
    only. ``None`` (no check) for a wildcard bind in any spelling (``0.0.0.0``,
    ``0``, ``::``, ``::0``, empty), whose own name the server cannot know."""
    address = _address(bind_host)
    if address is None:  # a host name
        if is_loopback(bind_host):
            return _LOOPBACK_NAMES
        return frozenset({_host_name(bind_host)})
    if address.is_unspecified:
        return None
    name = _host_name(str(address))
    if address.is_loopback:
        return _LOOPBACK_NAMES | {name}
    return frozenset({name})


def _address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """*host* as an IP address (with the short IPv4 forms ``0``, ``127.1`` the
    system accepts), or None for a host name."""
    host = host.strip("[]")
    if host in _WILDCARDS:
        return ipaddress.IPv4Address("0.0.0.0")
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except OSError:
        return None


def _host_name(host: str) -> str:
    host = host.lower()
    return f"[{host}]" if ":" in host and not host.startswith("[") else host


# --------------------------------------------------------------------------- #
# Header checks
# --------------------------------------------------------------------------- #


def repeated_header(names: Iterable[str], extra: Iterable[str] = ()) -> str | None:
    """The first of :data:`SINGLE_HEADERS` (and *extra*, lowercase) among the
    header *names* of a request, in order, that is sent twice: whoever reads
    the first and whoever reads the last would disagree."""
    single = SINGLE_HEADERS | frozenset(extra)
    seen: set[str] = set()
    for name in names:
        name = name.lower()
        if name in single:
            if name in seen:
                return name
            seen.add(name)
    return None


def host_ok(headers: Mapping[str, str], hosts: frozenset[str] | None, port: int) -> bool:
    """Whether the ``Host`` of *headers* names a server on *port* whose names
    are *hosts* (from :func:`allowed_hosts`; ``None`` accepts any)."""
    if hosts is None:
        return True
    host = headers.get("host", "").lower()
    name, sep, given = host.rpartition(":")
    if not sep or "]" in given:  # no port: only the default one would match
        name, given = host, ""
    wanted = str(port) if port != 80 else ""
    return name in hosts and given in {wanted, str(port)}


def token_in_url(query: str, token: str) -> bool:
    """Whether the query string *query* carries *token*, or a key a token is
    usually sent under: refused even with a good header, URLs end up in logs."""
    if not query:
        return False
    if token in unquote(query):
        return True
    return any(key.lower() in _URL_TOKEN_KEYS for key, _ in parse_qsl(query, True))


def token_leaked(target: str, token: str) -> bool:
    """Whether a request target (path and query) carries *token*: in the path or
    the query, raw or percent-encoded up to twice, or under a usual token key."""
    _, _, query = target.partition("?")
    seen = target
    for _ in range(3):
        if token in seen:
            return True
        seen = unquote(seen)
    return token_in_url(query, token) or token_in_url(unquote(query), token)


def bearer_ok(headers: Mapping[str, str], token: str) -> bool:
    """Whether *headers* carry ``Authorization: Bearer <token>``, compared in
    constant time over equal-length inputs: no timing tells how much matched."""
    scheme, _, given = headers.get("authorization", "").strip().partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(given.strip().encode(), token.encode())
