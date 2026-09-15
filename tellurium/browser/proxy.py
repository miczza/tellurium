"""Local proxy forwarder for authenticated proxy connections."""

from __future__ import annotations

import asyncio
import base64
import logging
from urllib.parse import urlparse

logger = logging.getLogger("tellurium")


def parse_proxy_url(url: str) -> dict:
    parsed = urlparse(url)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "",
        "port": parsed.port or (1080 if "socks" in (parsed.scheme or "") else 8080),
        "username": parsed.username,
        "password": parsed.password,
    }


class ProxyForwarder:
    """HTTP proxy forwarder that adds Proxy-Authorization to upstream."""

    def __init__(self, upstream_host: str, upstream_port: int, username: str, password: str):
        self._upstream_host = upstream_host
        self._upstream_port = upstream_port
        self._username = username
        self._password = password
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("Forwarder not started")
        return self._server.sockets[0].getsockname()[1]

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, "127.0.0.1", 0)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def _auth_header(self) -> str:
        creds = base64.b64encode(f"{self._username}:{self._password}".encode()).decode()
        return f"Proxy-Authorization: Basic {creds}\r\n"

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            first_line = await reader.readline()
            if not first_line:
                writer.close()
                return
            if first_line.upper().startswith(b"CONNECT"):
                await self._handle_connect(first_line, reader, writer)
            else:
                await self._handle_forward(first_line, reader, writer)
        except Exception:
            logger.debug("ProxyForwarder client error", exc_info=True)
        finally:
            try:
                writer.close()
            except Exception:  # noqa: BLE001 - socket cleanup
                pass

    async def _handle_connect(self, first_line, reader, writer):
        # Read remaining headers from client
        while True:
            line = await reader.readline()
            if line == b"\r\n" or not line:
                break
        # Connect to upstream
        up_reader, up_writer = await asyncio.open_connection(
            self._upstream_host, self._upstream_port
        )
        # Send CONNECT with auth
        up_writer.write(first_line)
        up_writer.write(self._auth_header().encode())
        up_writer.write(b"\r\n")
        await up_writer.drain()
        # Read upstream response
        await up_reader.readline()
        while True:
            line = await up_reader.readline()
            if line == b"\r\n" or not line:
                break
        # Tell client tunnel is up
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        # Bidirectional relay
        await self._relay(reader, writer, up_reader, up_writer)

    async def _handle_forward(self, first_line, reader, writer):
        up_reader, up_writer = await asyncio.open_connection(
            self._upstream_host, self._upstream_port
        )
        up_writer.write(first_line)
        up_writer.write(self._auth_header().encode())
        while True:
            line = await reader.readline()
            up_writer.write(line)
            if line == b"\r\n" or not line:
                break
        await up_writer.drain()
        # Relay response
        try:
            while True:
                data = await up_reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass

    async def _relay(self, r1, w1, r2, w2):
        async def _pipe(src, dst):
            try:
                while True:
                    data = await src.read(65536)
                    if not data:
                        break
                    dst.write(data)
                    await dst.drain()
            except (ConnectionError, asyncio.CancelledError):
                pass

        await asyncio.gather(_pipe(r1, w2), _pipe(r2, w1), return_exceptions=True)
