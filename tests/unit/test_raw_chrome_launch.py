"""RawChrome over a BrowserProcess: one wait for Chrome's first answer (the
spawn's), and a kill through the process object."""

from __future__ import annotations

import types

import pytest

from tellurium.browser import process as process_module
from tellurium.browser import raw_chrome
from tellurium.browser.raw_chrome import RawChrome


class _SilentTransport:
    """A pipe that never answers: a second wait for Chrome would hang on it."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(data)

    async def recv(self) -> dict:
        raise AssertionError("RawChrome must not wait for Chrome again after spawn")

    async def close(self) -> None:
        pass


async def test_the_launch_waits_once_for_chrome(monkeypatch):
    transport = _SilentTransport()
    killed = []

    async def compose(self, proc):
        return None

    async def spawn(self, chrome_path, flags, log, env):
        self.process = types.SimpleNamespace(pid=4242, poll=lambda: None)
        self.transport = transport
        return transport

    monkeypatch.setattr(raw_chrome.LaunchPlan, "compose", compose)
    monkeypatch.setattr(raw_chrome.LaunchPlan, "chrome_path", "chrome", raising=False)
    monkeypatch.setattr(process_module.BrowserProcess, "spawn", spawn)
    monkeypatch.setattr(process_module.BrowserProcess, "kill", lambda self: killed.append(self))
    raw = await RawChrome.launch(geoip=False)
    assert transport.sent == []
    raw.kill()
    assert killed == [raw._proc]
    assert raw_chrome.READY_TIMEOUT == process_module.READY_TIMEOUT


@pytest.fixture(autouse=True)
def _no_close(monkeypatch):
    async def close(self):
        return None

    monkeypatch.setattr(process_module.BrowserProcess, "close", close)
