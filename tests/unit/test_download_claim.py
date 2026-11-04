"""Downloads whose frame no filter knows, handed to the waiter whose owner finds it."""

from __future__ import annotations

import asyncio
from pathlib import Path

from tellurium.browser.download import Downloads


def _downloads(tmp_path: Path) -> Downloads:
    downloads = Downloads()
    downloads._folders[None] = (tmp_path, False)
    return downloads


def _owner(answer: bool, asked: list[str]):
    async def owns(frame_id: str) -> bool:
        asked.append(frame_id)
        await asyncio.sleep(0.05)
        return answer

    return owns


async def test_progress_reported_while_the_owner_looks_is_kept(tmp_path):
    downloads, asked = _downloads(tmp_path), []
    waiter = downloads.expect(lambda frame: False, owns=_owner(True, asked), timeout=5)
    async with waiter as info:
        downloads._on_will_begin({"guid": "g1", "frameId": "NESTED", "url": "u"})
        downloads._on_progress({"guid": "g1", "state": "completed", "receivedBytes": 3})
    download = await info.value
    assert asked == ["NESTED"]
    assert download.state == "completed" and download.received_bytes == 3
    assert await download.path(timeout=1) == tmp_path / "g1"
    assert not downloads._unclaimed


async def test_the_first_owner_that_finds_the_frame_takes_it(tmp_path):
    downloads, asked = _downloads(tmp_path), []
    other = downloads.expect(lambda frame: False, owns=_owner(False, asked), timeout=5)
    mine = downloads.expect(lambda frame: False, owns=_owner(True, asked), timeout=5)
    downloads._waiters += [other, mine]  # other waits first
    downloads._on_will_begin({"guid": "g2", "frameId": "NESTED", "url": "u"})
    await asyncio.gather(*downloads._claims)
    assert asked == ["NESTED", "NESTED"]
    assert mine._future.result().guid == "g2" and not other._future.done()


async def test_an_owner_that_fails_does_not_take_it(tmp_path):
    downloads = _downloads(tmp_path)

    async def broken(frame_id: str) -> bool:
        raise ConnectionError("the tab went away")

    waiter = downloads.expect(lambda frame: False, owns=broken, timeout=0.3)
    downloads._waiters.append(waiter)
    downloads._on_will_begin({"guid": "g3", "frameId": "NESTED", "url": "u"})
    await asyncio.gather(*downloads._claims)
    assert not waiter._future.done() and not downloads._active and not downloads._unclaimed
