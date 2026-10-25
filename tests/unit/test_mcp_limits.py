"""How many browsers the HTTP server runs: a cap per client and one for the
whole server, with a clear error past them; closed or failed launches give
their place back. Without Chrome."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")

from tellurium.mcp.clients import ClientPools  # noqa: E402
from tellurium.mcp.config import HttpConfig, ServerConfig  # noqa: E402
from tellurium.mcp.limits import SessionBudget  # noqa: E402
from tellurium.mcp.results import ToolError  # noqa: E402


class _FakeSession:
    persistent = False

    def __init__(self, sid: str):
        self.id = sid

    async def close(self):
        pass


def _clients(tmp_path, per_client=2, total=3) -> ClientPools:
    http = HttpConfig(max_sessions_per_client=per_client, max_sessions=total)
    clients = ClientPools(ServerConfig(home=tmp_path, http=http), idle_timeout=None)
    return clients


def _fake_launches(pool, fail=False):
    count = iter(range(1000))

    async def launch():
        await asyncio.sleep(0)
        if fail:
            raise RuntimeError("chrome did not start")
        return _FakeSession(f"temp-{next(count)}")

    pool._launch_temp = launch


async def _open(clients, client_id, n=1):
    async with clients.use(client_id) as pool:
        if not hasattr(pool, "_faked"):
            _fake_launches(pool)
            pool._faked = True
        return [(await pool.open(None))[0] for _ in range(n)]


async def test_a_client_past_its_cap_gets_a_clear_error(tmp_path):
    async with _clients(tmp_path, per_client=2, total=10) as clients:
        await _open(clients, "a", 2)
        with pytest.raises(ToolError, match="2 sessions open.*session-close"):
            await _open(clients, "a")
        await _open(clients, "b", 2)  # another client has its own cap


async def test_the_server_past_its_cap_gets_a_clear_error(tmp_path):
    async with _clients(tmp_path, per_client=2, total=3) as clients:
        await _open(clients, "a", 2)
        await _open(clients, "b")
        with pytest.raises(ToolError, match="server already runs 3 sessions"):
            await _open(clients, "c")


async def test_a_closed_session_gives_its_place_back(tmp_path):
    async with _clients(tmp_path, per_client=1, total=1) as clients:
        (opened,) = await _open(clients, "a")
        async with clients.use("a") as pool:
            await pool.close(opened.id)
        await _open(clients, "b")


async def test_a_dropped_client_gives_its_places_back(tmp_path):
    async with _clients(tmp_path, per_client=2, total=2) as clients:
        await _open(clients, "a", 2)
        await clients.drop("a")
        await _open(clients, "b", 2)


async def test_a_failed_launch_gives_its_place_back(tmp_path):
    async with _clients(tmp_path, per_client=1, total=1) as clients:
        async with clients.use("a") as pool:
            _fake_launches(pool, fail=True)
            with pytest.raises(RuntimeError):
                await pool.open(None)
            _fake_launches(pool)
            await pool.open(None)


def test_budget_counts_places():
    budget = SessionBudget(1)
    budget.take()
    with pytest.raises(ToolError):
        budget.take()
    budget.release()
    budget.take()


def test_defaults_are_4_per_client_16_in_all():
    http = HttpConfig()
    assert (http.max_sessions_per_client, http.max_sessions) == (4, 16)
