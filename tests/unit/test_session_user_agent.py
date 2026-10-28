"""A session saved with its own ``--user-agent`` among the launch args opens
from ``tellurium mcp`` and ``tellurium login``: they launch with stealth, which
refuses that flag, so for such a session they launch without it (its own
User-Agent is its identity), instead of failing with a ValueError that
suggests a stealth=False neither lets one choose."""

from __future__ import annotations

import json

import pytest

import tellurium
from tellurium import Session
from tellurium.session import login_command, stealth_choice

_UA = "--user-agent=Mozilla/5.0 Custom"


def _saved(folder, args):
    folder.mkdir(parents=True)
    payload = {"name": folder.name, "seed": 7, "metadata": {}, "launch": {"args": args}}
    (folder / "session.json").write_text(json.dumps(payload))
    return Session(folder.name, path=str(folder))


def test_stealth_unless_the_session_sets_its_own_user_agent(tmp_path):
    assert stealth_choice.notice(Session("a", path=str(tmp_path / "a"))) is None
    assert stealth_choice.notice(_saved(tmp_path / "b", ["--lang=it"])) is None
    assert "without stealth" in stealth_choice.notice(_saved(tmp_path / "c", [_UA]))


class _FakeTab:
    closed = False


class _FakeBrowser:
    def __init__(self):
        self.main_tab = _FakeTab()
        self.tabs = [self.main_tab]

    async def get_cookies(self, domain=None):
        return []

    async def set_cookies(self, cookies):
        pass

    async def close(self):
        pass


@pytest.fixture
def launched(monkeypatch):
    seen: list[dict] = []

    async def launch(**kwargs):
        if kwargs.get("stealth"):
            from tellurium.stealth.engine import refuse_user_agent_arg

            refuse_user_agent_arg(kwargs.get("args"))
        seen.append(kwargs)
        return _FakeBrowser()

    monkeypatch.setattr(tellurium.Browser, "launch", launch)
    return seen


async def test_tellurium_login_opens_it(tmp_path, launched, monkeypatch, capsys):
    _saved(tmp_path / "acct", [_UA])

    async def done_at_once(browser, tab, stdin, keeper=None):
        pass

    async def no_keeper(browser):
        return None

    monkeypatch.setattr(login_command, "_until_done", done_at_once)
    monkeypatch.setattr(login_command, "_open_keeper", no_keeper)
    await login_command.login("acct", directory=str(tmp_path))
    assert launched[0]["stealth"] is False
    assert _UA in launched[0]["args"]
    err = capsys.readouterr().err
    assert "without stealth" in err and "--user-agent" in err


async def test_mcp_opens_it(tmp_path, launched):
    pytest.importorskip("mcp")
    from tellurium.mcp.config import ServerConfig
    from tellurium.mcp.sessions import SessionPool, _session_open

    config = ServerConfig(home=tmp_path)
    _saved(config.sessions_dir / "acct", [_UA])
    async with SessionPool(config) as pool:
        reply = await _session_open(pool, {"name": "acct"})
        again = await _session_open(pool, {"name": "acct"})
    assert launched[0]["stealth"] is False
    assert _UA in launched[0]["args"]
    assert "without stealth" in reply.text and "--user-agent" in reply.text
    assert "without stealth" in again.text  # every reply about this session says it


async def test_mcp_keeps_stealth_for_the_others(tmp_path, launched):
    pytest.importorskip("mcp")
    from tellurium.mcp.config import ServerConfig
    from tellurium.mcp.sessions import SessionPool

    config = ServerConfig(home=tmp_path)
    async with SessionPool(config) as pool:
        await pool.open("acct")
        await pool.open(None)
    assert [k["stealth"] for k in launched] == [True, True]
