"""Fake Chromes for the hang probe's unit tests: a pipe that never answers,
one that answers late, and what the probe reads of a ``BrowserProcess``."""

from __future__ import annotations

import asyncio
import json

from tellurium.cdp.transport._base import CDPTransport


class SilentChrome(CDPTransport):
    """A pipe whose Chrome takes every command and never answers."""

    def __init__(self):
        self.sent: list[dict] = []
        self._never = asyncio.Event()

    async def send(self, data: bytes) -> None:
        self.sent.append(json.loads(data.rstrip(b"\0")))

    async def recv(self) -> dict:
        await self._never.wait()
        raise EOFError

    async def close(self) -> None:
        pass


class LateChrome(SilentChrome):
    """A pipe whose Chrome answers every command after *delay* seconds."""

    def __init__(self, delay: float):
        super().__init__()
        self._replies: asyncio.Queue = asyncio.Queue()
        self._delay = delay

    async def send(self, data: bytes) -> None:
        await super().send(data)
        loop = asyncio.get_running_loop()
        msg_id = self.sent[-1]["id"]
        loop.call_later(self._delay, self._replies.put_nowait, {"id": msg_id, "result": {}})

    async def recv(self) -> dict:
        return await self._replies.get()


class ProbedChrome:
    """What the probe reads of a ``BrowserProcess``: its pipe and its process."""

    def __init__(self, transport, process):
        self.transport, self.process = transport, process
