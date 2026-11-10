"""Downloads against a real Chrome: owned folders, per-context folders, waiters."""

import asyncio
import glob
import os
import tempfile

import pytest

from tellurium import Browser
from tellurium.browser.download import DownloadError
from tests.integration.conftest import DOWNLOAD_BODY
from tests.private_temp import FAILING_EXECUTABLE, private_temp
from tests.timeout_scale import scaled

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def private_tempdir(monkeypatch, tmp_path_factory):
    """Temp dirs of this test alone, so leftovers are ours (short: Chrome's
    singleton socket path must fit in 108 bytes)."""
    tmp_path_factory.getbasetemp()
    with private_temp(monkeypatch) as root:
        yield root


def expect_download(tab, timeout: float | None = None):
    """Wait for a download of this tab (30 s, scaled, by default)."""
    return tab.expect_download(timeout=scaled(30) if timeout is None else timeout)


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
        frame = browser.downloads.expect(lambda frame_id: frame_id != tab._target_id)
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
        assert browser.downloads._waiters == []
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
        await Browser.launch(headless=True, executable=FAILING_EXECUTABLE)
    assert made and not os.path.exists(made[0])


async def _started(download, timeout: float | None = None):
    """Wait until Chrome has written part of *download* (5 s, scaled, by default)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + (scaled(5) if timeout is None else timeout)
    while download.received_bytes == 0 and loop.time() < deadline:
        await asyncio.sleep(0.05)
    assert download.received_bytes > 0


async def _slow_download(tab):
    async with expect_download(tab) as info:
        await _click(tab, "#slow")
    download = await info.value
    await _started(download)
    return download


async def test_chrome_dying_fails_waits_at_once(local_server):
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.get(local_server + "/download.html")
        download = await _slow_download(tab)
        waiting = asyncio.ensure_future(download.path(timeout=20))
        pending = expect_download(tab, timeout=20)
        await pending.__aenter__()
        browser._proc.process.kill()
        with pytest.raises(DownloadError):
            await asyncio.wait_for(waiting, 5)
        with pytest.raises(DownloadError):
            await asyncio.wait_for(pending.value, 5)
    finally:
        await browser.close()


async def test_close_cancels_downloads_leaving_no_partial_file(local_server, tmp_path):
    browser = await Browser.launch(headless=True, downloads_dir=str(tmp_path))
    tab = await browser.get(local_server + "/download.html")
    download = await _slow_download(tab)
    assert list(tmp_path.iterdir()), "the partial file should exist mid-download"
    await browser.close()
    assert list(tmp_path.iterdir()) == []
    assert download.state == "canceled"


async def test_cancel_removes_the_partial_file(local_server, tmp_path):
    browser = await Browser.launch(headless=True, downloads_dir=str(tmp_path))
    try:
        tab = await browser.get(local_server + "/download.html")
        download = await _slow_download(tab)
        await download.cancel()
        assert list(tmp_path.iterdir()) == []
    finally:
        await browser.close()


async def test_a_raising_filter_fails_only_its_waiter(local_server):
    browser = await Browser.launch(headless=True)
    try:
        tab = await browser.get(local_server + "/download.html")
        broken = browser.downloads.expect(lambda frame_id: 1 / 0)
        await broken.__aenter__()
        async with expect_download(tab, timeout=scaled(10)) as info:
            await _click(tab, "#report")
        assert (await info.value).suggested_filename == "report.csv"
        with pytest.raises(ZeroDivisionError):
            await broken.value
    finally:
        await browser.close()


async def test_relative_downloads_dir_is_made_absolute(local_server, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    browser = await Browser.launch(headless=True, downloads_dir="rel")
    try:
        context = await browser.new_context(downloads_dir="ctx")
        assert context.downloads_dir == tmp_path / "ctx"
        tab = await browser.get(local_server + "/download.html")
        async with expect_download(tab) as info:
            await _click(tab, "#report")
        assert (await (await info.value).path()).parent == tmp_path / "rel"
    finally:
        await browser.close()


async def test_an_unfiltered_waiter_follows_the_download_context(local_server, tmp_path):
    browser = await Browser.launch(headless=True)
    try:
        context = await browser.new_context(downloads_dir=str(tmp_path))
        tab = await context.new_tab(local_server + "/download.html")
        async with browser.downloads.expect() as info:
            await _click(tab, "#slow")
        download = await info.value
        assert download.context_id == context.context_id
        await _started(download)
        await download.cancel()
        assert download.state == "canceled"
        assert list(tmp_path.iterdir()) == []
    finally:
        await browser.close()


async def test_closing_a_context_fails_its_waits(local_server, tmp_path):
    browser = await Browser.launch(headless=True)
    try:
        context = await browser.new_context(downloads_dir=str(tmp_path))
        tab = await context.new_tab(local_server + "/download.html")
        download = await _slow_download(tab)
        waiting = asyncio.ensure_future(download.path(timeout=20))
        pending = expect_download(tab, timeout=20)
        await pending.__aenter__()
        other = expect_download(browser.main_tab, timeout=20)
        await other.__aenter__()
        await context.close()
        with pytest.raises(DownloadError, match="context"):
            await asyncio.wait_for(waiting, 5)
        with pytest.raises(DownloadError, match="context"):
            await asyncio.wait_for(pending.value, 5)
        assert other in browser.downloads._waiters, "another context's waiter survives"
        assert list(tmp_path.iterdir()) == []
    finally:
        await browser.close()


async def test_a_download_nobody_waits_for_lands_in_the_folder(local_server, tmp_path):
    browser = await Browser.launch(headless=True, downloads_dir=str(tmp_path))
    try:
        tab = await browser.get(local_server + "/download.html")
        await _click(tab, "#report")
        for _ in range(int(scaled(5) / 0.05)):
            files = [p for p in tmp_path.iterdir() if p.is_file()]
            if files and files[0].read_bytes() == DOWNLOAD_BODY:
                break
            await asyncio.sleep(0.05)
        assert [p.read_bytes() for p in tmp_path.iterdir()] == [DOWNLOAD_BODY]
        assert browser.downloads._active == {}
        assert browser.downloads._waiters == []
    finally:
        await browser.close()


async def test_a_hostile_filename_stays_in_the_folder(local_server, tmp_path):
    keep = tmp_path / "keep"
    browser = await Browser.launch(headless=True, downloads_dir=str(keep))
    try:
        tab = await browser.get(local_server + "/download.html")
        url = local_server + "/download/..%2F..%2Fevil.csv"
        async with expect_download(tab) as info:
            await tab.eval(f"location.href = {url!r}")
        download = await info.value
        assert "/" not in download.suggested_filename
        path = await download.path()
        assert path.parent == keep and path.name == download.guid
    finally:
        await browser.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep"]
