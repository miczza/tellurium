"""SessionPool: many named identities side by side, each its own Chrome.

An identity is a :class:`~tellurium.session.Session` in a folder of the pool
directory (its profile, cookies and fingerprint seed). :meth:`SessionPool.open`
starts it, but never more than ``max_browsers`` at a time across the pool: a
slot is taken before Chrome starts and given back only after it is closed, on
error and cancellation too, and an open still waiting for a slot can be
cancelled. A name is claimed in the pool before the wait, so the same
identity opened twice fails at once (:class:`SessionBusyError`), as does one
another process holds (its session lock), instead of queueing for a slot.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from tellurium.session import lock as session_lock
from tellurium.session import profile_release
from tellurium.session.errors import SessionBusyError
from tellurium.session.session import _MANAGED_LAUNCH_KEYS, Session

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_SESSION_FILE = "session.json"


class SessionPool:
    """The identities under *directory*, at most *max_browsers* open at once.

    *launch* are the :meth:`Session.start` keyword arguments of every open
    (``headless=True``, ``stealth=True``, ...); those given to :meth:`open`
    win over them.
    """

    def __init__(self, directory: str | os.PathLike, *, max_browsers: int = 4, **launch: Any):
        if max_browsers < 1:
            raise ValueError(f"max_browsers must be at least 1, got {max_browsers!r}")
        bad = _MANAGED_LAUNCH_KEYS & launch.keys()
        if bad:
            raise TypeError(f"the pool manages these parameters itself: {sorted(bad)}")
        self.directory = os.path.abspath(os.fspath(directory))
        self.max_browsers = max_browsers
        self._launch = dict(launch)
        self._slots = asyncio.Semaphore(max_browsers)
        self._claimed: set[str] = set()  # names being opened, open or being deleted

    def path(self, name: str) -> str:
        """The folder of identity *name*; :class:`ValueError` for a name that is
        not 1-64 letters, digits, ``.``, ``_`` or ``-`` starting with a letter
        or digit (so it never leaves the pool directory)."""
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise ValueError(f"invalid session name {name!r}")
        return os.path.join(self.directory, name)

    async def list(self) -> list[str]:
        """The names of the identities in the pool, sorted."""
        return await asyncio.to_thread(self._names)

    async def create(self, name: str, *, seed: int | None = None) -> Session:
        """A new identity *name* (with *seed*, else a random one), saved at
        once; :class:`FileExistsError` if the pool has it already."""
        path = self.path(name)
        return await asyncio.to_thread(self._create, name, path, seed)

    async def get(self, name: str) -> Session:
        """The :class:`Session` of identity *name*, to add validators, a login
        or metadata before :meth:`open`; :class:`FileNotFoundError` if absent."""
        path = self.path(name)
        return await asyncio.to_thread(_load, name, path)

    async def delete(self, name: str) -> None:
        """Remove identity *name* and its folder. :class:`SessionBusyError` if
        it is open, here or in another process (the folder stays);
        :class:`FileNotFoundError` if the pool has no such identity."""
        path = self.path(name)
        with self._claim(name, path):
            if not os.path.isdir(path):
                raise FileNotFoundError(f"no session named {name!r} in {self.directory}")
            lock = session_lock.SessionLock(path)
            await lock.acquire_async()
            try:
                chrome = await profile_release.wait(os.path.join(path, "chrome"))
                if chrome is not None:
                    raise SessionBusyError(path, chrome)
                # Out of the way under the lock: whoever comes next finds no
                # session there, never one half removed.
                grave = os.path.join(self.directory, f".{name}.deleted-{uuid.uuid4().hex}")
                if sys.platform == "win32":
                    lock.release()  # Windows renames no folder with an open file
                os.rename(path, grave)
            finally:
                lock.release()
            await asyncio.to_thread(shutil.rmtree, grave)

    @asynccontextmanager
    async def open(self, session: str | Session, **launch: Any) -> AsyncIterator[Any]:
        """Start identity *session* (a name, created if missing, or a
        :class:`Session` of this pool) and yield its Browser; closed on exit.

        Waits for a free slot while ``max_browsers`` are open; the slot is
        held from before Chrome starts until it is closed. The session's
        ``session.json`` is written when it has none (so its seed lasts);
        otherwise saving it is up to the caller, as with :meth:`Session.start`.
        """
        if isinstance(session, Session):
            name, path = session.name, self.path(session.name)
            if os.path.abspath(session.path) != path:
                raise ValueError(f"session at {session.path} is not in the pool {self.directory}")
        else:
            name, path, session = session, self.path(session), None
        with self._claim(name, path):
            # Before the wait for a slot: a session busy elsewhere fails now.
            session = await asyncio.to_thread(_prepare, name, path, session)
            async with self._slots:
                async with session.start(**{**self._launch, **launch}) as browser:
                    yield browser

    @contextmanager
    def _claim(self, name: str, path: str) -> Iterator[None]:
        if name in self._claimed:
            raise SessionBusyError(path, os.getpid())
        self._claimed.add(name)
        try:
            yield
        finally:
            self._claimed.discard(name)

    def _names(self) -> list[str]:
        try:
            entries = os.scandir(self.directory)
        except FileNotFoundError:
            return []
        with entries:
            return sorted(e.name for e in entries if _NAME.fullmatch(e.name) and e.is_dir())

    def _create(self, name: str, path: str, seed: int | None) -> Session:
        os.makedirs(self.directory, exist_ok=True)
        os.mkdir(path)  # FileExistsError: the pool has it
        with _held(path):
            if os.path.exists(os.path.join(path, _SESSION_FILE)):
                raise FileExistsError(f"session {name!r} was just created elsewhere")
            session = Session(name, path=path, seed=seed)
            session.save()
            return session


def _load(name: str, path: str) -> Session:
    if not os.path.isdir(path):
        raise FileNotFoundError(f"no session named {name!r} at {path}")
    return Session(name, path=path)


def _prepare(name: str, path: str, session: Session | None) -> Session:
    """Under the session lock (:class:`SessionBusyError` if held elsewhere):
    load the session of a name, and save one that has no ``session.json``."""
    with _held(path):
        if session is None:
            session = Session(name, path=path)
        if not os.path.exists(os.path.join(path, _SESSION_FILE)):
            session.save()
        return session


@contextmanager
def _held(path: str) -> Iterator[None]:
    """The session lock of *path* for a moment, from a worker thread: tried
    again for a little while, as a probe holds it for an instant."""
    lock = session_lock.SessionLock(path)
    deadline = time.monotonic() + session_lock.PATIENCE
    while True:
        try:
            lock.acquire()
            break
        except SessionBusyError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.002)
    try:
        yield
    finally:
        lock.release()
