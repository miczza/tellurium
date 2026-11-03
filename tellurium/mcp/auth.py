"""Who may talk to ``tellurium mcp --http``: the checks every HTTP request
passes before it reaches MCP, on an ASGI scope.

The token file, the bind address and the header checks are those of
:mod:`tellurium.access` (token required on loopback too, only in the
``Authorization: Bearer`` header, compared in constant time; ``Host`` naming
the bind address). A browser always sends ``Origin`` on the requests a page
makes, and MCP clients are not web pages: any ``Origin`` is refused (no CORS,
so no preflight to get wrong).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tellurium.access import (
    TOKEN_BYTES,
    TokenFileError,
    allowed_hosts,
    bearer_ok,
    host_ok,
    is_loopback,
    load_or_create_token,
    parse_bind,
    repeated_header,
    token_in_url,
)

__all__ = [
    "ENDPOINT",
    "TOKEN_BYTES",
    "Guard",
    "Refusal",
    "TokenFileError",
    "allowed_hosts",
    "is_loopback",
    "load_or_create_token",
    "parse_bind",
]

ENDPOINT = "/mcp"
# Headers sent at most once besides Host, Origin and Authorization: they decide
# the MCP session and the protocol.
_MCP_SINGLE_HEADERS = frozenset({"mcp-session-id", "mcp-protocol-version"})


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
    """The checks for a server bound to port *port*, *hosts* from
    :func:`allowed_hosts`."""

    token: str
    hosts: frozenset[str] | None
    port: int

    def check(self, scope: dict[str, Any]) -> Refusal | None:
        """``None`` when the HTTP request *scope* may reach MCP, else why not.
        Order: repeated headers, Host and Origin (a page must learn nothing),
        the URL, the token, the path."""
        repeated = repeated_header(
            (k.decode("latin-1") for k, _ in scope.get("headers", [])), _MCP_SINGLE_HEADERS
        )
        if repeated:
            return Refusal(400, f"Header {repeated} sent more than once")
        headers = _headers(scope)
        if not host_ok(headers, self.hosts, self.port):
            return Refusal(403, "Host not allowed (this server answers only on its bind address)")
        if "origin" in headers:
            return Refusal(
                403, "Requests from web pages are refused: MCP clients are not web pages"
            )
        if token_in_url(scope.get("query_string", b"").decode("latin-1"), self.token):
            return Refusal(
                400, "Never put the token in the URL: send it in the Authorization header"
            )
        if not bearer_ok(headers, self.token):
            return Refusal(
                401,
                "Missing or wrong token: send 'Authorization: Bearer <token>' "
                "(the token is in the mcp-token file of the server's home)",
                ((b"www-authenticate", b"Bearer"),),
            )
        if scope.get("path") != ENDPOINT:
            return Refusal(404, f"Not found: the MCP endpoint is {ENDPOINT}")
        return None


def _headers(scope: dict[str, Any]) -> dict[str, str]:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
