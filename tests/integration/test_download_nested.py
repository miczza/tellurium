"""P3 part B — downloads from iframes nested inside a cross-site iframe (OOPIF).

Their frames are reported to the OOPIF's own session only: the tab learns them when
a download of an unknown frame begins, from the frame trees of its OOPIFs.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from tests.integration.conftest import DOWNLOAD_BODY
from tests.private_temp import private_temp


@pytest.fixture(autouse=True)
def private_tempdir(monkeypatch, tmp_path_factory):
    """Temp dirs of this test alone (short: Chrome's singleton socket path must fit)."""
    tmp_path_factory.getbasetemp()
    with private_temp(monkeypatch) as root:
        yield root


def _host(local_server: str, inner: str | None) -> str:
    query = f"?inner={quote(inner, safe='')}" if inner else ""
    return f"{local_server}/download_nested_host.html{query}"


@pytest.mark.parametrize("inner", ["download", "same site", "third site"])
async def test_download_from_an_iframe_inside_an_oopif(
    any_browser, local_server, other_server, inner
):
    url = {
        "download": None,  # the nested iframe's src is the download: it never commits
        "same site": "/download_nested_inner.html",
        "third site": f"{other_server}/download_nested_inner.html",
    }[inner]
    tab = any_browser.main_tab
    async with tab.expect_download(timeout=15) as info:
        await tab.get(_host(local_server, url))
    download = await info.value
    assert download.suggested_filename == ("never.csv" if url is None else "inner.csv")
    assert (await download.path()).read_bytes() == DOWNLOAD_BODY


async def test_another_tab_does_not_take_a_nested_download(browser, local_server):
    first = browser.main_tab
    second = await browser.new_tab("about:blank")
    with pytest.raises(TimeoutError):
        async with second.expect_download(timeout=4):
            async with first.expect_download(timeout=10) as mine:
                await first.get(_host(local_server, "/download_nested_inner.html"))
            assert (await mine.value).suggested_filename == "inner.csv"
