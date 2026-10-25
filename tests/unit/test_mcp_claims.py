"""Named sessions shared on disk between the pools of different MCP clients:
one Chrome per profile, and a clear error for the second client."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import pytest

pytest.importorskip("mcp")

from tellurium.mcp import sessions  # noqa: E402
from tellurium.mcp.claims import SessionClaims  # noqa: E402
from tellurium.mcp.config import ServerConfig  # noqa: E402
from tellurium.mcp.results import ToolError  # noqa: E402


class _FakeBrowser:
    tabs: list = []


class _FakeSession:
    started: list[str] = []
    fail_start = False

    def __init__(self, name, path):
        self.name = name

    @asynccontextmanager
    async def start(self, **options):
        if _FakeSession.fail_start:
            raise RuntimeError("chrome did not start")
        _FakeSession.started.append(self.name)
        try:
            yield _FakeBrowser()
        finally:
            _FakeSession.started.remove(self.name)

    def save(self):
        pass


@pytest.fixture
def fake_session(monkeypatch):
    _FakeSession.started = []
    _FakeSession.fail_start = False
    monkeypatch.setattr(sessions, "Session", _FakeSession)
    return _FakeSession


def _pools(tmp_path, n=2):
    claims = SessionClaims()
    config = ServerConfig(home=tmp_path)
    return [sessions.SessionPool(config, claims=claims) for _ in range(n)]


async def test_second_client_opening_the_same_name_gets_a_clear_error(tmp_path, fake_session):
    a, b = _pools(tmp_path)
    await a.open("github")
    with pytest.raises(ToolError, match="already open by another MCP client"):
        await b.open("github")
    assert fake_session.started == ["github"]  # never two Chrome on one profile


async def test_name_is_free_again_once_closed(tmp_path, fake_session):
    a, b = _pools(tmp_path)
    await a.open("github")
    await a.close("github")
    session, created = await b.open("github")
    assert created and session.id == "github"


async def test_close_all_frees_the_names(tmp_path, fake_session):
    a, b = _pools(tmp_path)
    await a.open("github")
    await a.open("gitlab")
    await a.close_all()
    await b.open("github")
    await b.open("gitlab")


async def test_a_failed_launch_frees_the_name(tmp_path, fake_session):
    a, b = _pools(tmp_path)
    fake_session.fail_start = True
    with pytest.raises(RuntimeError):
        await a.open("github")
    fake_session.fail_start = False
    await b.open("github")


async def test_same_client_reopening_gets_its_own_session(tmp_path, fake_session):
    (a,) = _pools(tmp_path, 1)
    first, _ = await a.open("github")
    again, created = await a.open("github")
    assert again is first and not created


def test_pools_of_one_server_share_the_claims(tmp_path):
    a, b = _pools(tmp_path)
    assert a._claims is b._claims


async def test_name_stays_claimed_while_its_close_runs(tmp_path, fake_session, monkeypatch):
    a, b = _pools(tmp_path)
    opened, _ = await a.open("github")
    real_close = opened.close
    gate = asyncio.Event()

    async def slow_close():
        await gate.wait()
        await real_close()

    monkeypatch.setattr(opened, "close", slow_close)
    closing = asyncio.ensure_future(a.close("github"))
    await asyncio.sleep(0)
    with pytest.raises(ToolError, match="another MCP client"):
        await b.open("github")
    gate.set()
    await closing
    await b.open("github")


def test_claims_release_only_by_the_owner():
    claims = SessionClaims()
    a, b = object(), object()
    claims.take("x", a)
    claims.take("x", a)  # idempotent for the owner
    claims.release("x", b)  # not b's: no effect
    with pytest.raises(ToolError):
        claims.take("x", b)
    claims.release("x", a)
    claims.take("x", b)
