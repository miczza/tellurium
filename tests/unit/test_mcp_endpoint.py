"""The HTTP endpoint's cap on requests that passed the guard, without a server."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from tellurium.mcp import auth, http_transport  # noqa: E402

TOKEN = "A" * 43


class _Manager:
    def __init__(self):
        self.release = asyncio.Event()

    async def handle_request(self, scope, receive, send):
        await self.release.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})


def _scope(token: str = TOKEN):
    headers = [(b"host", b"127.0.0.1:8765"), (b"authorization", f"Bearer {token}".encode())]
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "query_string": b"",
        "headers": headers,
    }


async def _status(endpoint, scope) -> int:
    sent = []

    async def send(message):
        sent.append(message)

    await endpoint(scope, None, send)
    return sent[0]["status"]


async def test_only_requests_past_the_guard_take_a_place(monkeypatch):
    monkeypatch.setattr(http_transport, "CONCURRENCY", 1)
    manager = _Manager()
    guard = auth.Guard(TOKEN, auth.allowed_hosts("127.0.0.1"), 8765)
    endpoint = http_transport.GuardedEndpoint(guard, manager, clients=None)
    busy = asyncio.ensure_future(_status(endpoint, _scope()))
    await asyncio.sleep(0)
    assert await _status(endpoint, _scope("wrong" * 9)) == 401  # refused before the cap
    assert await _status(endpoint, _scope()) == 503
    manager.release.set()
    assert await busy == 200
    assert endpoint.active == 0
    manager.release.set()
    assert await _status(endpoint, _scope()) == 200
