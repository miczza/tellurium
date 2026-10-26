"""A named session survives a restart in a new process: cookies with no expiry
included, and the one written right before the browser closed."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_CHILD = str(Path(__file__).with_name("session_child.py"))
_TIMEOUT = 90.0


async def _run_child(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        _CHILD,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), _TIMEOUT)
    except BaseException:
        proc.kill()
        await proc.wait()
        raise
    assert proc.returncode == 0, err.decode(errors="replace")[-2000:]
    return out.decode()


async def test_cookies_survive_a_restart_in_another_process(tmp_path, local_server):
    path = str(tmp_path / "child")
    await _run_child("write", path, local_server)
    names = json.loads((await _run_child("read", path)).strip().splitlines()[-1])
    assert "late" in names  # written right before close()
    assert "http_sso" in names  # HttpOnly, no expiry, from Set-Cookie
    assert "js_sso" in names  # no expiry, from document.cookie


async def test_cookies_with_no_expiry_outlive_a_second_restart(tmp_path, local_server):
    """Put back at start, they are kept again at the next close."""
    path = str(tmp_path / "child")
    await _run_child("write", path, local_server)
    await _run_child("read", path)
    names = json.loads((await _run_child("read", path)).strip().splitlines()[-1])
    assert {"http_sso", "js_sso", "late"} <= set(names)


async def test_a_partitioned_cookie_comes_back_partitioned(tmp_path):
    """CHIPS with no expiry: Chrome drops it on restart, cookies.json brings it
    back in its partition, and one without SameSite comes back without."""
    from tellurium import Cookie, Session

    partition = {"topLevelSite": "https://other.test", "hasCrossSiteAncestor": True}
    chips = Cookie(
        name="chips",
        value="1",
        domain="example.test",
        secure=True,
        same_site="None",
        partition_key=partition,
    )
    loose = Cookie(name="loose", value="2", domain="example.test", same_site=None)
    path = str(tmp_path / "s")
    async with Session("s", path=path).start(headless=True) as browser:
        await browser.set_cookies([chips, loose])
    async with Session("s", path=path).start(headless=True) as browser:
        back = {c.name: c for c in await browser.get_cookies("example.test")}
    assert back["chips"].partition_key == partition
    assert back["chips"].same_site == "None"
    assert back["loose"].same_site is None
