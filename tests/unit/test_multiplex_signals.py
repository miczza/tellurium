"""``tellurium multiplex`` where the platform has fewer signal tools (Windows: no
SIGHUP, no ``pthread_sigmask``, no ``loop.add_signal_handler``): the CLI still
imports, and Ctrl-C still closes everything instead of crashing."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import types

import pytest

from tellurium.multiplexer import command

pytestmark = pytest.mark.skipif(not hasattr(os, "kill"), reason="sends itself a signal")


def test_the_cli_imports_without_sighup_nor_pthread_sigmask():
    script = (
        "import signal; del signal.SIGHUP; del signal.pthread_sigmask; "
        "import tellurium.cli; from tellurium.multiplexer import command; "
        "print(command._stop_signals())"
    )
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stderr
    found = done.stdout.strip()
    assert "SIGINT" in found and "SIGTERM" in found and "SIGHUP" not in found


class _Mux:
    """Serves until cancelled, then takes a while to close (as the pool does)."""

    url: str | None = None
    token_file = "token"

    def __init__(self) -> None:
        self.closed = False
        self.cancels = 0

    def status(self) -> dict:
        return {"size": 1}

    async def serve(self, host: str, port: int) -> None:
        self.url = f"http://{host}:{port}"
        try:
            await asyncio.get_running_loop().create_future()
        except asyncio.CancelledError:
            self.cancels += 1
            while True:  # a second Ctrl-C does not cut the closing short
                try:
                    await asyncio.sleep(0.3)
                    break
                except asyncio.CancelledError:
                    self.cancels += 1
            self.closed = True
            raise


async def test_ctrl_c_closes_everything_without_add_signal_handler(monkeypatch):
    fake = types.SimpleNamespace(
        **{
            name: getattr(signal, name)
            for name in ("SIGINT", "SIGTERM", "SIG_IGN", "signal", "getsignal")
        }
    )
    monkeypatch.setattr(command, "signal", fake)
    loop = asyncio.get_running_loop()

    def unsupported(*_args):
        raise NotImplementedError

    monkeypatch.setattr(loop, "add_signal_handler", unsupported)
    monkeypatch.setattr(loop, "remove_signal_handler", unsupported)
    saved = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    mux = _Mux()
    try:
        serving = asyncio.ensure_future(command._serve(mux, "127.0.0.1", 9339, 0))
        while mux.url is None:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        os.kill(os.getpid(), signal.SIGINT)
        await asyncio.sleep(0.05)
        os.kill(os.getpid(), signal.SIGINT)  # again, while it closes
        await asyncio.wait_for(serving, 10)
        assert mux.closed and mux.cancels == 2
        # Closed: a late signal is ignored, not the default (which would kill).
        assert signal.getsignal(signal.SIGINT) == signal.SIG_IGN
        os.kill(os.getpid(), signal.SIGINT)
    finally:
        for signum, handler in saved.items():
            signal.signal(signum, handler)
