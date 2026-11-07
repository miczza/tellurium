"""A separate process holding a named session, for the tests that need two.

``python session_child.py write PATH URL`` opens the session, loads the pages
that set cookies with no expiry, writes one more cookie right before closing,
saves and exits. ``python session_child.py rotate PATH`` writes ``tok=old``,
waits until Chrome's cookie store has it on disk, rotates it to ``tok=new`` and
closes with a Chrome that dies before committing that last change (as it can
on SIGTERM). ``python session_child.py read PATH`` opens it again and prints
its cookies as a JSON object, name to value. ``python session_child.py hold
PATH`` opens it, prints ``ready`` and waits until it is killed.

The tests start it with :func:`child_env`: killed with SIGKILL, it cannot
remove its temporary folders, so they go in the test's own tmp_path.
:func:`start_holder` and :func:`kill_holder` run a ``hold`` child on every system.
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import json
import os
import signal
import sqlite3
import sys
import time
import uuid

from tellurium import Cookie, Session


async def write(path: str, base: str) -> None:
    session = Session("child", path=path)
    async with session.start(headless=True) as browser:
        tab = await browser.get(f"{base}/session-cookie")
        await tab.get(f"{base}/session_cookie.html")
        await tab.eval("document.cookie = 'late=1; path=/; max-age=3600'")
        await session.save_now()


async def read(path: str) -> None:
    session = Session("child", path=path)
    async with session.start(headless=True) as browser:
        jar = {c.name: c.value for c in await browser.get_cookies("127.0.0.1")}
    print(json.dumps(jar, sort_keys=True), flush=True)


_LINKS: list[str] = []
_SELF = os.path.abspath(__file__)


async def start_holder(path: str) -> asyncio.subprocess.Process:
    """A ``hold`` child of the session at *path*, once it has printed ``ready``."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        _SELF,
        "hold",
        path,
        env=child_env(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        # Its Chrome too can be killed as a group (POSIX; on Windows that
        # Chrome exits by itself once the holder's end of its pipe is gone).
        start_new_session=sys.platform != "win32",
    )
    try:
        line = await asyncio.wait_for(proc.stdout.readline(), 60)
    except BaseException:
        kill_holder(proc)
        await proc.wait()
        raise
    assert line.strip() == b"ready"
    return proc


def kill_holder(proc: asyncio.subprocess.Process) -> None:
    """Kill *proc* and, on POSIX, its Chrome with it (its process group)."""
    try:
        if sys.platform == "win32":
            proc.kill()  # TerminateProcess: no group to kill
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):  # gone already
        pass


def child_env(path: str) -> dict[str, str]:
    """The environment for a child holding the session at *path*: its temp
    directory is a hidden folder next to it (inside the test's tmp_path; a
    pool skips it). On POSIX it is reached through a short link in the short
    temp root, since Chrome's singleton socket path must stay short; Windows
    has no such socket. The links go when the tests end."""
    from tests.private_temp import SHORT_ROOT, child_temp_env

    tmpdir = os.path.join(os.path.dirname(os.path.abspath(path)), ".child-tmp")
    os.makedirs(tmpdir, exist_ok=True)
    if sys.platform == "win32":
        return child_temp_env(tmpdir)
    link = os.path.join(SHORT_ROOT, f"tlrc-{uuid.uuid4().hex[:10]}")
    os.symlink(tmpdir, link)
    if not _LINKS:
        atexit.register(_unlink_all)
    _LINKS.append(link)
    return child_temp_env(link)


def _unlink_all() -> None:
    for link in _LINKS:
        with contextlib.suppress(OSError):
            os.unlink(link)


def _token(value: str) -> Cookie:
    return Cookie(name="tok", value=value, domain="127.0.0.1", expires=time.time() + 3600)


def _on_disk(path: str, name: str) -> bool:
    """Whether Chrome's cookie database of the session has a cookie *name*."""
    for db in ("Default/Network/Cookies", "Default/Cookies"):
        file = os.path.join(path, "chrome", db)
        if not os.path.exists(file):
            continue
        try:
            with sqlite3.connect(f"file:{file}?mode=ro", uri=True, timeout=1) as conn:
                rows = conn.execute("SELECT 1 FROM cookies WHERE name = ?", (name,)).fetchall()
        except sqlite3.Error:
            return False  # being written: ask again
        return bool(rows)
    return False


def _kill_tree(pid: int) -> None:
    """Stop Chrome and all its processes (the network service holds the
    cookie store), then kill them: none gets to write anything more."""
    tree, i = [pid], 0
    while i < len(tree):
        for task in os.listdir(f"/proc/{tree[i]}/task"):
            with open(f"/proc/{tree[i]}/task/{task}/children") as f:
                tree += [int(child) for child in f.read().split()]
        i += 1
    for sig in (signal.SIGSTOP, signal.SIGKILL):
        for each in tree:
            try:
                os.kill(each, sig)
            except ProcessLookupError:
                pass


async def rotate(path: str) -> None:
    session = Session("child", path=path)
    async with session.start(headless=True) as browser:
        await browser.set_cookies([_token("old")])
        # Chrome's cookie store commits every 30 s, or after 512 changes: 600
        # (one per host, under every per-host cap) commit tok=old, and leave
        # the changes after the 512th pending, tok=new among them.
        far = time.time() + 3600
        flush = [
            Cookie(name="f", value="1", domain=f"f{i}.flush.test", expires=far) for i in range(600)
        ]
        await browser.set_cookies(flush)
        deadline = time.monotonic() + 60
        while not await asyncio.to_thread(_on_disk, path, "tok"):
            if time.monotonic() > deadline:
                raise SystemExit("Chrome never committed tok=old")
            await asyncio.sleep(0.2)
        await browser.set_cookies([_token("new")])
        close = browser.close

        async def die_then_close() -> None:  # after the session read the jar
            target = os.readlink(os.path.join(path, "chrome", "SingletonLock"))
            _kill_tree(int(target.rpartition("-")[2]))
            await close()

        browser.close = die_then_close


async def hold(path: str) -> None:
    session = Session("child", path=path)
    async with session.start(headless=True):
        print("ready", flush=True)
        await asyncio.Event().wait()


def main() -> None:
    mode, path, *rest = sys.argv[1:]
    runs = {"write": lambda: write(path, rest[0]), "read": lambda: read(path)}
    runs["hold"] = lambda: hold(path)
    runs["rotate"] = lambda: rotate(path)
    asyncio.run(runs[mode]())


if __name__ == "__main__":
    main()
