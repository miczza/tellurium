import os, subprocess, sys
import pytest
from tellurium import Browser
from tests.integration.test_downloads import _slow_download

pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize("i", range(25))
async def test_race(local_server, tmp_path, i):
    browser = await Browser.launch(headless=True, downloads_dir=str(tmp_path))
    try:
        tab = await browser.get(local_server + "/download.html")
        d = await _slow_download(tab)
        before = sorted(p.name for p in tmp_path.iterdir())
        await d.cancel()
        after = sorted(p.name for p in tmp_path.iterdir())
        print("GUID", d.guid, "before", before, "after", after)
        assert after == []
    finally:
        await browser.close()
