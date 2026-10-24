"""Downloads against a real Chrome: owned folders, per-context folders, waiters."""

import asyncio
import glob
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from tellurium import Browser
from tellurium.browser.download import DownloadError
from tests.integration.conftest import DOWNLOAD_BODY

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def private_tempdir(monkeypatch, tmp_path_factory):
    """Temp dirs of this test alone, so leftovers are ours (short: Chrome's
    singleton socket path must fit in 108 bytes)."""
    tmp_path_factory.getbasetemp()
    root = Path(tempfile.mkdtemp(prefix="tlr", dir="/tmp"))
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    monkeypatch.setenv("TMPDIR", str(root))
    yield root
    shutil.rmtree(root, ignore_errors=True)


def expect_download(tab, timeout=30):
    """What Tab.expect_download (part B) will do: wait for a download of this tab."""
    browser = tab._browser
    context_id = next((c.context_id for c in browser._contexts.values() if tab in c._tabs), None)
    return browser._downloads.expect(
        lambda frame_id: frame_id == tab._target_id, context_id=context_id, timeout=timeout
    )


async def _click(tab, selector):
    await tab.eval(f"document.querySelector('{selector}').click()")


def _download_dirs() -> list[str]:
    return glob.glob(os.path.join(tempfile.gettempdir(), "tellurium_dl_*"))


async def test_download_lands_in_an_owned_folder_removed_on_close(local_server):
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.get(local_server + "/download.html")
        async with expect_download(tab) as info:
            await _click(tab, "#report")
        download = await info.value
        assert download.url == local_server + "/download/report.csv"
        assert download.suggested_filename == "report.csv"
        path = await download.path()
        assert path.read_bytes() == DOWNLOAD_BODY
        assert download.state == "completed"
        owned = _download_dirs()
        assert len(owned) == 1 and str(path).startswith(owned[0])
    finally:
        await browser.close()
    assert not path.exists()
    assert _download_dirs() == []


async def test_save_as_copies_the_file(local_server, tmp_path):
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.get(local_server + "/download.html")
        async with expect_download(tab) as info:
            await _click(tab, "#report")
        target = tmp_path / "nested" / "report.csv"
        saved = await (await info.value).save_as(target)
        assert saved == target
    finally:
        await browser.close()
    assert target.read_bytes() == DOWNLOAD_BODY


async def test_downloads_dir_is_kept_after_close(local_server, tmp_path):
    keep = tmp_path / "keep"
    browser = await Browser.launch(headless=True, downloads_dir=str(keep))
    try:
        tab = await browser.get(local_server + "/download.html")
        async with expect_download(tab) as info:
            await _click(tab, "#report")
        path = await (await info.value).path()
        assert path.parent == keep
    finally:
        await browser.close()
    assert path.read_bytes() == DOWNLOAD_BODY
    assert _download_dirs() == []


async def test_each_context_has_its_own_folder(local_server, tmp_path):
    browser = await Browser.launch(headless=True)
    try:
        context = await browser.new_context()
        kept = await browser.new_context(downloads_dir=str(tmp_path / "ctx"))
        assert context.downloads_dir != kept.downloads_dir
        paths = []
        for ctx in (context, kept):
            tab = await ctx.new_tab(local_server + "/download.html")
            async with expect_download(tab) as info:
                await _click(tab, "#report")
            paths.append(await (await info.value).path())
        assert paths[0].parent == context.downloads_dir
        assert paths[1].parent == tmp_path / "ctx"
        await context.close()
        assert not context.downloads_dir.exists()
        await kept.close()
        assert paths[1].read_bytes() == DOWNLOAD_BODY
    finally:
        await browser.close()


async def test_context_folder_follows_a_kept_browser_folder(local_server, tmp_path):
    browser = await Browser.launch(headless=True, downloads_dir=str(tmp_path))
    try:
        context = await browser.new_context()
        assert context.downloads_dir.parent == tmp_path
        await context.close()
        assert context.downloads_dir.is_dir()
    finally:
        await browser.close()


async def test_cancel_stops_a_download(local_server):
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.get(local_server + "/download.html")
        async with expect_download(tab) as info:
            await _click(tab, "#slow")
        download = await info.value
        await download.cancel()
        assert download.state == "canceled"
        with pytest.raises(DownloadError, match="canceled"):
            await download.path()
        with pytest.raises(DownloadError):
            await download.save_as("unused.bin")
    finally:
        await browser.close()


async def test_waiter_times_out_without_a_download(local_server):
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.get(local_server + "/download.html")
        with pytest.raises(TimeoutError, match="download"):
            async with expect_download(tab, timeout=0.5):
                pass
    finally:
        await browser.close()


async def test_waiter_ignores_downloads_of_other_frames(local_server):
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.get(local_server + "/download.html")
        frame = browser._downloads.expect(lambda frame_id: frame_id != tab._target_id)
        async with frame, expect_download(tab) as info:
            await tab.eval(
                "document.getElementById('frame').contentDocument.getElementById('inner').click()"
            )
            inner = await frame.value
            await _click(tab, "#report")
        assert inner.suggested_filename == "inner.csv"
        assert (await info.value).suggested_filename == "report.csv"
    finally:
        await browser.close()


async def test_block_error_discards_the_waiter(local_server):
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.get(local_server + "/download.html")
        with pytest.raises(ValueError):
            async with expect_download(tab) as info:
                raise ValueError("boom")
        with pytest.raises(DownloadError):
            await info.value
        assert browser._downloads._waiters == []
    finally:
        await browser.close()


async def test_close_fails_a_pending_download(local_server):
    browser = await Browser.launch(headless=True)
    tab = await browser.get(local_server + "/download.html")
    async with expect_download(tab) as info:
        await _click(tab, "#slow")
    download = await info.value
    waiting = asyncio.ensure_future(download.path())
    await asyncio.sleep(0.2)
    await browser.close()
    with pytest.raises(DownloadError, match="closed"):
        await asyncio.wait_for(waiting, 5)


async def test_failed_launch_removes_the_owned_folder(monkeypatch):
    from tellurium.browser.process import BrowserProcess, LaunchError

    made = []
    original = BrowserProcess.make_downloads_dir
    monkeypatch.setattr(
        BrowserProcess, "make_downloads_dir", lambda self: made.append(original(self)) or made[-1]
    )
    with pytest.raises(LaunchError):
        await Browser.launch(headless=True, executable="/bin/false")
    assert made and not os.path.exists(made[0])
