"""Download.cancel returns once the partial file is gone: Chrome reports the
download canceled before its file thread deletes ``<guid>.crdownload``."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from tellurium.browser.download import Downloads


class _Chrome:
    """Answers ``Browser.cancelDownload`` with the canceled progress at once and
    deletes the partial file *delay* seconds later (never, with ``None``)."""

    def __init__(self, downloads: Downloads, partial: Path, delay: float | None) -> None:
        self.downloads, self.partial, self.delay = downloads, partial, delay

    async def send(self, method, params, timeout=None):
        assert method == "Browser.cancelDownload"
        self.downloads._on_progress({"guid": params["guid"], "state": "canceled"})
        if self.delay is not None:
            asyncio.get_running_loop().call_later(self.delay, self.partial.unlink)
        return {}


def _download(tmp_path: Path, delay: float | None):
    downloads = Downloads()
    downloads._folders[None] = (tmp_path, False)
    partial = tmp_path / "g1.crdownload"
    partial.write_bytes(b"part")
    downloads._session = _Chrome(downloads, partial, delay)
    waiter = downloads.expect(lambda frame: True, timeout=5)
    downloads._waiters.append(waiter)
    downloads._on_will_begin({"guid": "g1", "frameId": "F", "url": "u"})
    return waiter._future.result(), partial


async def test_cancel_waits_for_chrome_to_delete_the_partial_file(tmp_path):
    download, partial = _download(tmp_path, delay=0.3)
    await download.cancel()
    assert download.state == "canceled"
    assert not partial.exists()


async def test_a_partial_file_chrome_leaves_is_removed_within_the_timeout(tmp_path):
    download, partial = _download(tmp_path, delay=None)
    started = time.monotonic()
    await download.cancel(timeout=1.0)
    assert time.monotonic() - started < 1.5
    assert not partial.exists()
