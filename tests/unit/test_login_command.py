"""``tellurium login``: its command line, and Enter in the terminal."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

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


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX terminal")
async def test_enter_on_a_real_terminal_ends_the_wait():
    """A pty, as an interactive ``tellurium login`` has: the line is consumed."""
    import pty

    controller, terminal = pty.openpty()
    try:
        with os.fdopen(terminal, closefd=False) as stdin:
            assert stdin.isatty()
            waiter = asyncio.create_task(login_command.enter_pressed(stdin))
            await asyncio.sleep(0.2)
            assert not waiter.done()
            os.write(controller, b"\n")
            await asyncio.wait_for(waiter, 5)
    finally:
        os.close(controller)
        os.close(terminal)


async def test_enter_without_readers_is_read_in_a_thread(monkeypatch):
    """The Windows console branch: no add_reader, a daemon thread reads the line."""
    loop = asyncio.get_running_loop()

    def no_readers(fd, callback):
        raise NotImplementedError

    monkeypatch.setattr(loop, "add_reader", no_readers)
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
