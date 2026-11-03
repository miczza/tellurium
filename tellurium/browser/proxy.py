"""Local proxy forwarder for authenticated proxy connections."""

from __future__ import annotations

import asyncio
import base64
import hmac
import logging
import re
import secrets
import ssl
from urllib.parse import unquote, urlparse

logger = logging.getLogger("tellurium")

#: Proxy schemes Chrome understands in ``--proxy-server``.
_SCHEMES = ("http", "https", "socks4", "socks5")
#: What a URL scheme may look like (RFC 3986): anything else before "://" is user info.
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*")
_CHUNK = 65536
_MAX_HEADER_LINES = 200
_MAX_HEAD_BYTES = 64 * 1024
_CONNECT_TIMEOUT = 30.0
#: Seconds a new connection has to send its first request head. Later heads of a
#: keep-alive connection are not timed: only a client that showed the secret gets
#: there, and Chrome keeps idle proxy connections open for reuse.
_HEAD_TIMEOUT = 30.0
#: A header field name (RFC 9110 token): nothing else may stand before the colon.
_TOKEN = re.compile(rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_BAD_GATEWAY = b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
_GATEWAY_TIMEOUT = b"HTTP/1.1 504 Gateway Timeout\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
#: The user name of the forwarder's own credentials; the password is a secret per forwarder.
FORWARDER_USER = "tellurium"
_CHALLENGE = (
    b"HTTP/1.1 407 Proxy Authentication Required\r\n"
    b'Proxy-Authenticate: Basic realm="tellurium"\r\n'
    b"Content-Length: 0\r\nConnection: close\r\n\r\n"
)
#: What a refused client may still send (its request body) before the connection
#: closes: read and dropped, so the close does not reset the 407 away.
_REFUSED_DRAIN_BYTES = 1024 * 1024
_REFUSED_DRAIN_TIMEOUT = 1.0
#: Seconds the responses to requests already forwarded may still take, after a
#: later request of the same connection was refused, before it is closed.
_IN_FLIGHT_LIMIT = 30.0


def _split(url: str) -> tuple[str, str | None, str]:
    """``(scheme, userinfo or None, the rest)`` of a proxy URL. The user info
    ends at the *last* ``@``: a password may hold ``/``, ``@``, ``:``, ``#`` or
    ``?`` unencoded, and whatever follows that ``@`` is never a credential."""
    scheme, sep, rest = url.partition("://")
    if not sep or not _SCHEME.fullmatch(scheme):  # "://" inside a password, no scheme
        scheme, rest = "", url
    userinfo, at, host = rest.rpartition("@")
    return scheme, (userinfo if at else None), host


def redact_proxy_url(url: str | None) -> str | None:
    """*url* without its credentials (``user:password@``), for messages and status."""
    if not url:
        return url
    scheme, _, host = _split(url)
    return f"{scheme}://{host}" if scheme else host


def hide_credentials(text: str, url: str | None) -> str:
    """*text* with the user name and password of the proxy *url* masked, raw or
    percent-decoded: for error messages that may quote the URL."""
    if not url:
        return text
    _, userinfo, _ = _split(url)
    if not userinfo:
        return text
    user, _, password = userinfo.partition(":")
    secrets = {userinfo, password, unquote(password), user, unquote(user)}
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            text = text.replace(secret, "***")
    return text


def parse_proxy_url(url: str) -> dict:
    """Split a proxy URL; a bare ``host:port`` is an HTTP proxy. The password
    may hold unencoded ``/``, ``@``, ``:``, ``#`` or ``?``; errors never quote
    the credentials."""
    scheme, userinfo, host = _split(url)
    scheme = (scheme or "http").lower()
    if scheme not in _SCHEMES:
        raise ValueError(
            f"Unsupported proxy scheme {scheme!r} in {redact_proxy_url(url)!r}; "
            f"use one of {_SCHEMES}"
        )
    parsed = urlparse(f"{scheme}://{host}")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError(f"Bad proxy port in {redact_proxy_url(url)!r}") from None
    username = password = None
    if userinfo is not None:
        user, colon, secret = userinfo.partition(":")
        username = unquote(user)
        password = unquote(secret) if colon else None
    return {
        "scheme": scheme,
        "host": parsed.hostname or "",
        "port": port or (1080 if scheme.startswith("socks") else 8080),
        "username": username,
        "password": password,
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


class _Refused(Exception):
    """A request head without the forwarder's secret."""


class ProxyForwarder:
    """Local HTTP proxy that adds ``Proxy-Authorization`` to every upstream request.

    It is not an open proxy: every request head must carry the forwarder's own
    credentials (``tellurium`` and a random secret drawn per forwarder, see
    :attr:`auth_header`); without them the client gets ``407`` and the upstream
    is never contacted. Chrome answers that challenge through
    :class:`~tellurium.browser.proxy_auth.ProxyAuth`. The secret never appears
    in ``repr``, logs or errors.

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
        self._secret = secrets.token_urlsafe(32)
        token = base64.b64encode(f"{FORWARDER_USER}:{self._secret}".encode()).decode()
        self._expected = f"Basic {token}".encode()
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.Task] = set()
        #: Seconds the upstream has to answer a CONNECT before Chrome gets a 504.
        self.answer_timeout = _CONNECT_TIMEOUT
        #: Seconds a new connection has to send its first request head; then it is closed.
        self.head_timeout = _HEAD_TIMEOUT

    def __repr__(self) -> str:
        listening = self._server is not None
        port = f" port={self.port}" if listening else ""
        return f"<ProxyForwarder{port} upstream={self._upstream_host}:{self._upstream_port}>"

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("Forwarder not started")
        return self._server.sockets[0].getsockname()[1]

    @property
    def auth_header(self) -> str:
        """The ``Proxy-Authorization`` value (``Basic …``) that gets a client in."""
        return self._expected.decode()

    @property
    def credentials(self) -> tuple[str, str]:
        """``(user, secret)`` to answer the forwarder's challenge with."""
        return FORWARDER_USER, self._secret

    def _admits(self, head: list[bytes]) -> bool:
        """Whether *head* carries the forwarder's credentials (constant-time check).

        A head with a malformed header line (folded, whitespace before the
        colon, no colon) is refused: the check and the removal of the header
        (:meth:`_with_auth`) read names the same way, so no spelling of it
        can slip past both and carry the secret upstream.
        """
        if not all(_field_name(line) is not None for line in head[1:]):
            return False
        given = _header(head, b"proxy-authorization") or b""
        return hmac.compare_digest(given, self._expected)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)

    async def stop(self) -> None:
        """Stop listening and close every open connection (idempotent)."""
        server, self._server = self._server, None
        if server is None:
            return
        server.close()
        if hasattr(server, "close_clients"):  # Python 3.13+
            server.close_clients()
        closed = asyncio.ensure_future(server.wait_closed())
        try:
            # A connection accepted just now gets its handler a moment later:
            # sweep again until the server reports every connection closed.
            for _ in range(100):
                for task in list(self._clients):
                    task.cancel()
                await asyncio.gather(*self._clients, return_exceptions=True)
                if (await asyncio.wait({closed}, timeout=0.05))[0]:
                    return
            logger.debug("ProxyForwarder: connections still open after stop()")
        finally:
            closed.cancel()

    def _auth_line(self) -> bytes:
        creds = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
        return f"Proxy-Authorization: Basic {creds}\r\n".encode()

    def _with_auth(self, head: list[bytes]) -> bytes:
        """The request head with our credentials in place of any the client sent."""
        kept = [ln for ln in head[1:] if _field_name(ln) != b"proxy-authorization"]
        return b"".join([head[0], *kept]) + self._auth_line() + b"\r\n"

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
            try:
                head = await asyncio.wait_for(_read_head(reader), self.head_timeout)
            except TimeoutError:
                logger.debug("ProxyForwarder: no request head within %g s", self.head_timeout)
                return
            if head is None:
                return
            if not self._admits(head):
                raise _Refused
            try:
                up_reader, up_writer = await self._open_upstream()
            except (TimeoutError, OSError) as exc:
                logger.debug("ProxyForwarder cannot reach the upstream: %s", exc)
                writer.write(_BAD_GATEWAY)
                await writer.drain()
                return
            if head[0].upper().startswith(b"CONNECT"):
                await self._tunnel(head, reader, writer, up_reader, up_writer)
            else:
                await self._forward(head, reader, writer, up_reader, up_writer)
        except _Refused:
            logger.debug("ProxyForwarder refused a request without its credentials")
            await _refuse(reader, writer)
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
        """Copy every request of a keep-alive connection, credentials added.

        Each head is checked: one without the forwarder's credentials ends the
        connection with a ``407`` (:class:`_Refused`)."""
        while head is not None:
            if not self._admits(head):
                raise _Refused
            up.write(self._with_auth(head))
            await up.drain()
            await _copy_body(head, reader, up)
            head = await _read_head(reader)

    async def _forward(self, head, reader, writer, up_reader, up_writer) -> None:
        """Plain HTTP requests one way, the upstream's responses the other.

        A later request without the credentials stops the requests, but the
        responses to those already forwarded go on until the upstream is
        quiet for :data:`_REFUSED_DRAIN_TIMEOUT` (or closes): only then the
        ``407``, never after a response cut short. An upstream still sending
        after :data:`_IN_FLIGHT_LIMIT` seconds gets the connection closed,
        with no ``407``."""
        loop = asyncio.get_running_loop()
        heard = [loop.time()]  # when the upstream last sent something
        requests = asyncio.ensure_future(self._requests(head, reader, up_writer))
        responses = asyncio.ensure_future(_pipe(up_reader, writer, heard))
        try:
            await asyncio.wait([requests, responses], return_when=asyncio.FIRST_COMPLETED)
            if (
                requests.done()
                and not requests.cancelled()
                and isinstance(requests.exception(), _Refused)
                and not await _quiet(responses, heard)
            ):
                return  # still streaming: closed without a 407
        finally:
            for task in (requests, responses):
                task.cancel()
            await asyncio.gather(requests, responses, return_exceptions=True)
        for task in (requests, responses):
            if task.done() and not task.cancelled() and task.exception() is not None:
                raise task.exception()  # _Refused: the 407; else the handler logs it

    async def _tunnel(self, head, reader, writer, up_reader, up_writer) -> None:
        up_writer.write(self._with_auth(head))
        await up_writer.drain()
        try:
            answer = await asyncio.wait_for(_read_head(up_reader), self.answer_timeout)
        except TimeoutError:
            writer.write(_GATEWAY_TIMEOUT)
            await writer.drain()
            return
        if answer is None:
            raise ConnectionError("upstream closed before answering CONNECT")
        writer.write(b"".join(answer) + b"\r\n")
        parts = answer[0].split()
        if len(parts) < 2 or not parts[1].startswith(b"2"):
            await _copy_body(answer, up_reader, writer)  # the refusal, verbatim
            return
        await writer.drain()
        await _race(_pipe(reader, up_writer), _pipe(up_reader, writer))


async def _refuse(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Answer ``407`` and close, after dropping what the client still sends (bounded)."""
    try:
        writer.write(_CHALLENGE)
        await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()

        async def drain_input() -> None:
            left = _REFUSED_DRAIN_BYTES
            while left > 0 and (data := await reader.read(min(left, _CHUNK))):
                left -= len(data)

        await asyncio.wait_for(drain_input(), _REFUSED_DRAIN_TIMEOUT)
    except (TimeoutError, OSError, ConnectionError):
        pass


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
        if len(lines) > _MAX_HEADER_LINES or sum(map(len, lines)) > _MAX_HEAD_BYTES:
            raise ValueError("HTTP head too long")


def _field_name(line: bytes) -> bytes | None:
    """The lowercased name of a header line; None when the line is not a
    well-formed field (an obs-fold continuation, whitespace before the colon,
    no colon)."""
    name, sep, _ = line.partition(b":")
    if not sep or not _TOKEN.fullmatch(name):
        return None
    return name.lower()


def _header(head: list[bytes], name: bytes) -> bytes | None:
    for line in head[1:]:
        if _field_name(line) == name:
            return line.partition(b":")[2].strip()
    return None


async def _copy_body(
    head: list[bytes], reader: asyncio.StreamReader, up: asyncio.StreamWriter
) -> None:
    """Copy one message body, framed by ``Transfer-Encoding`` or ``Content-Length``.

    Streamed in pieces of at most 64 KiB: a declared size is never buffered.
    """
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
            await _copy_exact(reader, up, size + 2)  # data + CRLF
    else:
        await _copy_exact(reader, up, int(_header(head, b"content-length") or b"0"))
    await up.drain()


async def _copy_exact(reader: asyncio.StreamReader, up: asyncio.StreamWriter, n: int) -> None:
    while n > 0:
        data = await reader.read(min(n, _CHUNK))
        if not data:
            raise asyncio.IncompleteReadError(b"", n)
        up.write(data)
        await up.drain()
        n -= len(data)


async def _pipe(
    src: asyncio.StreamReader, dst: asyncio.StreamWriter, heard: list[float] | None = None
) -> None:
    """*src* to *dst* until *src* ends; *heard[0]* gets the loop time of each read."""
    loop = asyncio.get_running_loop()
    while data := await src.read(_CHUNK):
        if heard is not None:
            heard[0] = loop.time()
        dst.write(data)
        await dst.drain()


async def _quiet(responses: asyncio.Future, heard: list[float]) -> bool:
    """Wait until *responses* ends or its source has been silent for
    :data:`_REFUSED_DRAIN_TIMEOUT`: True; False past :data:`_IN_FLIGHT_LIMIT`."""
    loop = asyncio.get_running_loop()
    limit = loop.time() + _IN_FLIGHT_LIMIT
    while not responses.done():
        now = loop.time()
        if now - heard[0] >= _REFUSED_DRAIN_TIMEOUT:
            return True
        if now >= limit:
            return False
        wait = min(heard[0] + _REFUSED_DRAIN_TIMEOUT, limit) - now
        await asyncio.wait([responses], timeout=wait)
    return True


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
