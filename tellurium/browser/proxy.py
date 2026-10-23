"""Local proxy forwarder for authenticated proxy connections."""

from __future__ import annotations

import asyncio
import base64
import logging
import ssl
from urllib.parse import unquote, urlparse

logger = logging.getLogger("tellurium")

#: Proxy schemes Chrome understands in ``--proxy-server``.
_SCHEMES = ("http", "https", "socks4", "socks5")
_CHUNK = 65536
_MAX_HEADER_LINES = 200
_CONNECT_TIMEOUT = 30.0
_BAD_GATEWAY = b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"


def parse_proxy_url(url: str) -> dict:
    """Split a proxy URL; a bare ``host:port`` is an HTTP proxy."""
    parsed = urlparse(url if "://" in url else f"http://{url}")
    scheme = (parsed.scheme or "http").lower()
    if scheme not in _SCHEMES:
        raise ValueError(f"Unsupported proxy scheme {scheme!r} in {url!r}; use one of {_SCHEMES}")
    return {
        "scheme": scheme,
        "host": parsed.hostname or "",
        "port": parsed.port or (1080 if scheme.startswith("socks") else 8080),
        "username": unquote(parsed.username) if parsed.username is not None else None,
        "password": unquote(parsed.password) if parsed.password is not None else None,
    }


def proxy_server_flag(url: str) -> str:
    """The ``--proxy-server`` value for *url*: scheme kept, IPv6 host bracketed.

    Without a scheme Chrome takes the value for an HTTP proxy, so a SOCKS or
    HTTPS proxy would be spoken to in the wrong protocol.
    """
    info = parse_proxy_url(url)
    host = f"[{info['host']}]" if ":" in info["host"] else info["host"]
    return f"{info['scheme']}://{host}:{info['port']}"


def forwarder_for(url: str) -> ProxyForwarder | None:
    """The local forwarder an authenticated proxy needs, or None without credentials.

    Chrome cannot answer a proxy's auth challenge on its own, so the forwarder
    adds ``Proxy-Authorization``. It speaks HTTP to the upstream: SOCKS
    credentials are refused instead of being silently dropped.
    """
    info = parse_proxy_url(url)
    if not (info["username"] or info["password"]):
        return None
    if info["scheme"].startswith("socks"):
        raise ValueError(
            "SOCKS proxies with credentials are not supported (Chrome cannot "
            f"authenticate to SOCKS): {info['scheme']}://{info['host']}:{info['port']}"
        )
    return ProxyForwarder(
        info["host"],
        info["port"],
        info["username"] or "",
        info["password"] or "",
        tls=info["scheme"] == "https",
    )


class ProxyForwarder:
    """Local HTTP proxy that adds ``Proxy-Authorization`` to every upstream request.

    Plain HTTP requests share one upstream connection per client connection
    (keep-alive): each request head gets the credentials and its body is
    copied by its own framing (``Content-Length`` or chunked). ``CONNECT``
    tunnels are opened only when the upstream accepts them; any other answer
    (407, 502…) reaches Chrome verbatim. *tls* opens the upstream connection
    over TLS (an ``https://`` proxy).
    """

    def __init__(
        self,
        upstream_host: str,
        upstream_port: int,
        username: str,
        password: str,
        *,
        tls: bool = False,
    ):
        self._upstream_host = upstream_host
        self._upstream_port = upstream_port
        self._username = username
        self._password = password
        self._tls = tls
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.Task] = set()

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("Forwarder not started")
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)

    async def stop(self) -> None:
        """Stop listening and close every open connection (idempotent)."""
        server, self._server = self._server, None
        if server is None:
            return
        server.close()
        for task in list(self._clients):
            task.cancel()
        await asyncio.gather(*self._clients, return_exceptions=True)
        await server.wait_closed()

    def _auth_line(self) -> bytes:
        creds = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
        return f"Proxy-Authorization: Basic {creds}\r\n".encode()

    def _with_auth(self, head: list[bytes]) -> bytes:
        """The request head with our credentials in place of any the client sent."""
        lines = [ln for ln in head if not ln.lower().startswith(b"proxy-authorization:")]
        return b"".join(lines) + self._auth_line() + b"\r\n"

    async def _open_upstream(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        tls = {}
        if self._tls:
            tls = {"ssl": ssl.create_default_context(), "server_hostname": self._upstream_host}
        return await asyncio.wait_for(
            asyncio.open_connection(self._upstream_host, self._upstream_port, **tls),
            _CONNECT_TIMEOUT,
        )

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._clients.add(task)
        up_writer: asyncio.StreamWriter | None = None
        try:
            head = await _read_head(reader)
            if head is None:
                return
            try:
                up_reader, up_writer = await self._open_upstream()
            except (OSError, asyncio.TimeoutError) as exc:
                logger.debug("ProxyForwarder cannot reach the upstream: %s", exc)
                writer.write(_BAD_GATEWAY)
                await writer.drain()
                return
            if head[0].upper().startswith(b"CONNECT"):
                await self._tunnel(head, reader, writer, up_reader, up_writer)
            else:
                await _race(self._requests(head, reader, up_writer), _pipe(up_reader, writer))
        except Exception:  # noqa: BLE001 — one broken connection never stops the forwarder
            logger.debug("ProxyForwarder client error", exc_info=True)
        finally:
            self._clients.discard(task)
            for w in (writer, up_writer):
                if w is not None:
                    w.close()

    async def _requests(
        self, head: list[bytes] | None, reader: asyncio.StreamReader, up: asyncio.StreamWriter
    ) -> None:
        """Copy every request of a keep-alive connection, credentials added."""
        while head is not None:
            up.write(self._with_auth(head))
            await up.drain()
            await _copy_body(head, reader, up)
            head = await _read_head(reader)

    async def _tunnel(self, head, reader, writer, up_reader, up_writer) -> None:
        up_writer.write(self._with_auth(head))
        await up_writer.drain()
        answer = await _read_head(up_reader)
        if answer is None:
            raise ConnectionError("upstream closed before answering CONNECT")
        writer.write(b"".join(answer) + b"\r\n")
        parts = answer[0].split()
        if len(parts) < 2 or not parts[1].startswith(b"2"):
            length = _header(answer, b"content-length")
            if length is not None and length.isdigit():
                writer.write(await up_reader.readexactly(int(length)))
            await writer.drain()
            return
        await writer.drain()
        await _race(_pipe(reader, up_writer), _pipe(up_reader, writer))


async def _read_head(reader: asyncio.StreamReader) -> list[bytes] | None:
    """Start line and header lines (CRLF kept, blank line dropped); None on EOF."""
    lines: list[bytes] = []
    while True:
        line = await reader.readline()
        if not line:
            if lines:
                raise asyncio.IncompleteReadError(b"".join(lines), None)
            return None
        if line in (b"\r\n", b"\n"):
            if lines:
                return lines
            continue  # stray CRLF between keep-alive requests
        lines.append(line)
        if len(lines) > _MAX_HEADER_LINES:
            raise ValueError("HTTP head too long")


def _header(head: list[bytes], name: bytes) -> bytes | None:
    for line in head[1:]:
        key, sep, value = line.partition(b":")
        if sep and key.strip().lower() == name:
            return value.strip()
    return None


async def _copy_body(
    head: list[bytes], reader: asyncio.StreamReader, up: asyncio.StreamWriter
) -> None:
    """Copy one request body, framed by ``Transfer-Encoding`` or ``Content-Length``."""
    if (_header(head, b"transfer-encoding") or b"").lower().endswith(b"chunked"):
        while True:
            size_line = await reader.readline()
            up.write(size_line)
            size = int(size_line.split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while (trailer := await reader.readline()) not in (b"\r\n", b"\n", b""):
                    up.write(trailer)
                up.write(b"\r\n")
                break
            up.write(await reader.readexactly(size + 2))  # data + CRLF
            await up.drain()
    else:
        remaining = int(_header(head, b"content-length") or b"0")
        while remaining > 0:
            data = await reader.readexactly(min(remaining, _CHUNK))
            up.write(data)
            await up.drain()
            remaining -= len(data)
    await up.drain()


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    while data := await src.read(_CHUNK):
        dst.write(data)
        await dst.drain()


async def _race(*coros) -> None:
    """Run *coros* until the first ends (one side closed); cancel the rest."""
    tasks = [asyncio.ensure_future(c) for c in coros]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    for t in done:
        t.result()  # surface a protocol error to the caller's handler
