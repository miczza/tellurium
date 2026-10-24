"""Tab.expect_download with a real Chrome (local fixtures)."""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import pytest

from tellurium import Download, DownloadError, NavigationError
from tests.integration.conftest import DOWNLOAD_BODY

_INNER_CLICK = "document.getElementById('frame').contentDocument.getElementById('inner').click()"


@pytest.fixture(autouse=True)
def private_tempdir(monkeypatch, tmp_path_factory):
    """Temp dirs of this test alone (short: Chrome's singleton socket path must fit)."""
    tmp_path_factory.getbasetemp()  # pytest's own base stays where it was
    root = Path(tempfile.mkdtemp(prefix="tlr", dir="/tmp"))
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    monkeypatch.setenv("TMPDIR", str(root))
    yield root
    shutil.rmtree(root, ignore_errors=True)


async def test_download_started_by_a_ref_click(browser, local_server, tmp_path):
    tab = await browser.get(local_server + "/download.html")
    text = await tab.snapshot(interactive=True)
    ref = re.search(r'- link "Report" \[ref=(e\d+)\]', text).group(1)
    async with tab.expect_download() as info:
        await (await tab.select(f"@{ref}")).click()
    download = await info.value
    assert isinstance(download, Download)
    assert download.url == local_server + "/download/report.csv"
    assert download.suggested_filename == "report.csv"
    path = await download.path()
    assert path.read_bytes() == DOWNLOAD_BODY
    assert path.parent == browser._downloads.folder()
    copy = await download.save_as(tmp_path / "kept.csv")
    assert copy.read_bytes() == DOWNLOAD_BODY


async def test_download_from_a_same_process_iframe(browser, local_server):
    tab = await browser.get(local_server + "/download.html")
    async with tab.expect_download(timeout=10) as info:
        await tab.eval(_INNER_CLICK)
    download = await info.value
    assert download.suggested_filename == "inner.csv"
    assert (await download.path()).read_bytes() == DOWNLOAD_BODY


async def test_download_from_an_iframe_added_later(browser, local_server):
    tab = await browser.get(local_server + "/basic.html")
    await tab.eval(
        "const f = document.createElement('iframe');"
        'f.srcdoc = \'<a id="late" href="/download/late.csv">Late</a>\';'
        "document.body.append(f);"
        "new Promise(r => f.onload = r)"
    )
    async with tab.expect_download(timeout=10) as info:
        await tab.eval(
            "document.querySelector('iframe').contentDocument.getElementById('late').click()"
        )
    assert (await info.value).suggested_filename == "late.csv"


async def test_iframe_download_of_a_context_tab_lands_in_the_context_folder(
    browser, local_server, tmp_path
):
    context = await browser.new_context(downloads_dir=str(tmp_path / "ctx"))
    tab = await context.new_tab(local_server + "/download.html")
    async with tab.expect_download(timeout=10) as info:
        await tab.eval(_INNER_CLICK)
    download = await info.value
    assert download.context_id == context.context_id
    assert (await download.path()).parent == tmp_path / "ctx"


async def test_a_tab_does_not_take_another_tabs_download(browser, local_server):
    first = await browser.get(local_server + "/download.html")
    second = await browser.new_tab(local_server + "/download.html")
    with pytest.raises(TimeoutError, match="download"):
        async with first.expect_download(timeout=2), second.expect_download() as theirs:
            await second.eval(_INNER_CLICK)
            assert (await theirs.value).suggested_filename == "inner.csv"
    async with first.expect_download(timeout=10) as info:
        await first.eval("document.getElementById('report').click()")
    assert (await info.value).suggested_filename == "report.csv"


async def test_canceled_download(browser, local_server):
    tab = await browser.get(local_server + "/download.html")
    async with tab.expect_download() as info:
        await tab.eval("document.getElementById('slow').click()")
    download = await info.value
    await download.cancel()
    assert download.state == "canceled"
    with pytest.raises(DownloadError, match="canceled"):
        await download.path()


async def test_no_download_times_out(browser, local_server):
    tab = await browser.get(local_server + "/download.html")
    with pytest.raises(TimeoutError, match="0.5s"):
        async with tab.expect_download(timeout=0.5):
            pass


async def test_get_to_a_download_points_at_expect_download(browser, local_server):
    tab = browser.main_tab
    with pytest.raises(NavigationError, match=r"Tab\.expect_download\(\)"):
        await tab.get(local_server + "/download/report.csv")
