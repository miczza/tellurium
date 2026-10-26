"""``tellurium login``: its command line, and Enter in the terminal."""

from __future__ import annotations

import asyncio
import os

from tellurium import cli
from tellurium.session import login_command


async def test_enter_on_the_terminal_ends_the_wait():
    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(read_fd) as stdin:
            waiter = asyncio.create_task(login_command.enter_pressed(stdin))
            await asyncio.sleep(0.2)
            assert not waiter.done()
            os.write(write_fd, b"\n")
            await asyncio.wait_for(waiter, 5)
    finally:
        os.close(write_fd)


def test_cli_login_runs_the_login(monkeypatch, tmp_path, capsys):
    calls = []

    async def fake_login(name, url=None, *, directory, enter=False):
        calls.append((name, url, directory))
        return os.path.join(directory, name)

    monkeypatch.setattr(login_command, "login", fake_login)
    argv = ["tellurium", "login", "github", "https://github.com/login", "--dir", str(tmp_path)]
    monkeypatch.setattr("sys.argv", argv)
    cli.main()
    assert calls == [("github", "https://github.com/login", str(tmp_path))]
    assert "saved in" in capsys.readouterr().out


def test_cli_login_defaults_to_the_mcp_sessions_folder(monkeypatch, tmp_path):
    calls = []

    async def fake_login(name, url=None, *, directory, enter=False):
        calls.append((name, url, directory))
        return os.path.join(directory, name)

    monkeypatch.setattr(login_command, "login", fake_login)
    monkeypatch.setenv("TELLURIUM_HOME", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["tellurium", "login", "github"])
    cli.main()
    assert calls == [("github", None, str(tmp_path / "sessions"))]
