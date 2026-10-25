"""One session pool per MCP client over HTTP, without Chrome: isolation, the
end of a client's MCP session, the idle timeout and the shutdown."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from tellurium.mcp.clients import ClientPools  # noqa: E402
from tellurium.mcp.config import ServerConfig  # noqa: E402
from tellurium.mcp.results import ToolError  # noqa: E402


class _FakeSession:
    persistent = True

    def __init__(self, sid: str, close_delay: float = 0.01):
        self.id, self.close_delay, self.closed = sid, close_delay, False

    async def close(self):
        await asyncio.sleep(self.close_delay)
        self.closed = True


async def _pool(clients: ClientPools, client_id: str | None):
    async with clients.use(client_id) as pool:
        return pool


def _pools(tmp_path, idle: float | None = None) -> ClientPools:
    return ClientPools(ServerConfig(home=tmp_path, allow_eval=False), idle_timeout=idle)


async def test_each_client_gets_its_own_pool(tmp_path):
    async with _pools(tmp_path) as clients:
        pool_a, pool_b = await _pool(clients, "a"), await _pool(clients, "b")
        assert pool_a is not pool_b
        assert await _pool(clients, "a") is pool_a
        assert pool_a._claims is pool_b._claims  # named sessions are shared on disk


async def test_end_of_the_mcp_session_closes_and_saves_its_browsers(tmp_path):
    async with _pools(tmp_path) as clients:
        pool = await _pool(clients, "a")
        fake = _FakeSession("github")
        pool._sessions["github"] = fake
        await clients.drop("a")
        assert fake.closed and pool.sessions() == []
        assert await _pool(clients, "a") is not pool  # a fresh one if it ever calls again


async def test_idle_client_has_its_sessions_closed_and_gets_a_new_pool(tmp_path):
    async with _pools(tmp_path, idle=0.1) as clients:
        pool = await _pool(clients, "a")
        fake = _FakeSession("github")
        pool._sessions["github"] = fake
        await asyncio.sleep(0.4)
        assert fake.closed and pool.sessions() == []
        assert await _pool(clients, "a") is not pool


async def test_a_call_in_flight_is_not_idleness(tmp_path):
    async with _pools(tmp_path, idle=0.1) as clients:
        async with clients.use("a") as pool:
            fake = _FakeSession("github")
            pool._sessions["github"] = fake
            await asyncio.sleep(0.3)
            assert not fake.closed
        await asyncio.sleep(0.05)
        assert not fake.closed  # idleness counts from the end of the last call
        await asyncio.sleep(0.3)
        assert fake.closed


async def test_no_idle_timeout_keeps_sessions(tmp_path):
    async with _pools(tmp_path, idle=None) as clients:
        pool = await _pool(clients, "a")
        fake = _FakeSession("github")
        pool._sessions["github"] = fake
        await asyncio.sleep(0.2)
        assert not fake.closed


async def test_a_call_during_the_idle_close_waits_for_it(tmp_path):
    async with _pools(tmp_path, idle=0.05) as clients:
        pool = await _pool(clients, "a")
        fake = _FakeSession("github", close_delay=0.3)
        pool._sessions["github"] = fake
        await asyncio.sleep(0.15)  # the idle close has started, not finished
        assert not fake.closed
        await _pool(clients, "a")
        assert fake.closed  # the old pool let its profiles go first


async def test_shutdown_closes_every_client(tmp_path):
    clients = _pools(tmp_path)
    fakes = []
    async with clients:
        for cid in ("a", "b"):
            pool = await _pool(clients, cid)
            fakes.append(_FakeSession(f"s-{cid}"))
            pool._sessions[fakes[-1].id] = fakes[-1]
    assert all(f.closed for f in fakes)
    with pytest.raises(ToolError, match="shutting down"):
        await _pool(clients, "c")


async def test_a_request_without_an_mcp_session_is_refused(tmp_path):
    async with _pools(tmp_path) as clients:
        with pytest.raises(ToolError, match="MCP session"):
            await _pool(clients, None)


async def test_a_cancelled_drop_keeps_closing_and_shutdown_waits(tmp_path):
    clients = _pools(tmp_path)
    async with clients:
        pool = await _pool(clients, "a")
        fake = _FakeSession("github", close_delay=0.1)
        pool._sessions["github"] = fake
        dropping = asyncio.ensure_future(clients.drop("a"))
        await asyncio.sleep(0)
        dropping.cancel()
    assert fake.closed
