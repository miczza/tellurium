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
