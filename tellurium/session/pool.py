"""SessionPool: many named identities side by side, each its own Chrome.

An identity is a :class:`~tellurium.session.Session` in a folder of the pool
directory (its profile, cookies and fingerprint seed). :meth:`SessionPool.open`
starts it, but never more than ``max_browsers`` at a time across the pool: a
slot is taken before Chrome starts and given back only after it is closed, on
error and cancellation too, and an open still waiting for a slot can be
cancelled; the cap holds across event loops and threads (one ``asyncio.run``
after another, or several at once in threads). A name is claimed in the pool before the wait, so the same
identity opened twice fails at once (:class:`SessionBusyError`), as does one
another process holds (its session lock), instead of queueing for a slot.

Names are portable (:mod:`tellurium.session.names`): one that Windows cannot
hold, or that differs from another identity's only by case, is refused on
every system. A delete moves the folder away under the session lock, then
removes it; what an interrupted one leaves is removed by the next delete and
by the first call of a pool opened afterwards.
"""

from __future__ import annotations

import asyncio
import functools
import os
import shutil
import threading
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from tellurium.session import lock as session_lock
from tellurium.session import names, profile_release
from tellurium.session.errors import SessionBusyError
from tellurium.session.session import _MANAGED_LAUNCH_KEYS, Session
from tellurium.session.slots import Slots

_SESSION_FILE = "session.json"


class SessionPool:
    """The identities under *directory* (``~`` expanded), at most *max_browsers*
    open at once.

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
        self.directory = os.path.abspath(os.path.expanduser(os.fspath(directory)))
        self.max_browsers = max_browsers
        self._launch = dict(launch)
        self._slots = Slots(max_browsers)  # bound to no loop
        self._claims_lock = threading.Lock()  # _claimed, from any thread
        self._claimed: set[str] = set()  # case-folded names being opened, open or being deleted
        self._swept = False  # the leftovers of interrupted deletes are gone

    def path(self, name: str) -> str:
        """The folder of identity *name*; :class:`ValueError` for a name that is
        not portable (:mod:`tellurium.session.names`: 1-64 letters, digits,
        ``.``, ``_`` or ``-`` starting with a letter or digit, so it never
        leaves the pool directory; no Windows device name, no final dot)."""
        return os.path.join(self.directory, names.check(name))

    async def list(self) -> list[str]:
        """The names of the identities in the pool, sorted."""
        await self._sweep()
        return await asyncio.to_thread(self._names)

    async def create(self, name: str, *, seed: int | None = None) -> Session:
        """A new identity *name* (with *seed*, else a random one), saved at
        once; :class:`FileExistsError` if the pool has it already,
        :class:`ValueError` if it has one named so but for case."""
        path = self.path(name)
        await self._sweep()
        return await asyncio.to_thread(self._create, name, path, seed)

    async def get(self, name: str) -> Session:
        """The :class:`Session` of identity *name*, to add validators, a login
        or metadata before :meth:`open`; :class:`FileNotFoundError` if absent."""
        path = self.path(name)
        await self._sweep()
        return await asyncio.to_thread(self._load, name, path)

    async def delete(self, name: str) -> None:
        """Remove identity *name* and its folder. :class:`SessionBusyError` if
        it is open, here or in another process (the folder stays);
        :class:`FileNotFoundError` if the pool has no such identity."""
        path = self.path(name)
        await self._sweep()
        with self._claim(name, path):
            await asyncio.to_thread(names.check_folder, self.directory, name)
            if not os.path.isdir(path):
                raise FileNotFoundError(f"no session named {name!r} in {self.directory}")
            lock = session_lock.SessionLock(path)
            await lock.acquire_async()
            try:
                chrome = await profile_release.wait(os.path.join(path, "chrome"))
                if chrome is not None:
                    raise SessionBusyError(path, chrome)
                # Out of the way under the lock (beside the folder, so Windows
                # renames it too): whoever comes next finds no session there,
                # never one half removed.
                grave = os.path.join(self.directory, names.grave_name(name, uuid.uuid4().hex))
                await asyncio.to_thread(os.rename, path, grave)
            finally:
                lock.release()
            await asyncio.to_thread(_remove_graves, self.directory)

    @asynccontextmanager
    async def open(
        self, session: str | Session, *, create: bool = True, **launch: Any
    ) -> AsyncIterator[Any]:
        """Start identity *session* (a name, or a :class:`Session` of this
        pool) and yield its Browser; closed on exit. A missing identity is
        created (*create*), else :class:`FileNotFoundError`, before any wait.

        Waits for a free slot while ``max_browsers`` are open; the slot is
        held from before Chrome starts until it is closed. The session's
        ``session.json`` is written when it has none (so its seed lasts),
        checked again under the session lock once the slot is free (the
        identity may have been deleted meanwhile: written again with its seed,
        or :class:`FileNotFoundError` without *create*); otherwise saving it
        is up to the caller, as with :meth:`Session.start`.
        """
        if isinstance(session, Session):
            name, path = session.name, self.path(session.name)
            if os.path.abspath(session.path) != path:
                raise ValueError(f"session at {session.path} is not in the pool {self.directory}")
        else:
            name, path, session = session, self.path(session), None
        await self._sweep()
        with self._claim(name, path):
            # Before the wait for a slot: a session busy elsewhere fails now.
            session = await asyncio.to_thread(self._prepare, name, path, session, create)
            async with self._slots.slot():
                session._on_lock = functools.partial(_ensure, name, path, session, create)
                try:
                    async with session.start(**{**self._launch, **launch}) as browser:
                        yield browser
                finally:
                    session._on_lock = None

    @contextmanager
    def _claim(self, name: str, path: str) -> Iterator[None]:
        key = name.casefold()  # one folder on Windows and macOS
        with self._claims_lock:
            if key in self._claimed:
                raise SessionBusyError(path, os.getpid())
            self._claimed.add(key)
        try:
            yield
        finally:
            with self._claims_lock:
                self._claimed.discard(key)

    async def _sweep(self) -> None:
        """Once per pool: remove what deletes interrupted before (a process
        killed, a removal that failed) left in the directory."""
        if not self._swept:
            self._swept = True
            await asyncio.to_thread(_remove_graves, self.directory)

    def _names(self) -> list[str]:
        try:
            entries = os.scandir(self.directory)
        except FileNotFoundError:
            return []
        with entries:
            return sorted(
                e.name
                for e in entries
                if names.is_valid(e.name) and e.is_dir(follow_symlinks=False)
            )

    def _create(self, name: str, path: str, seed: int | None) -> Session:
        os.makedirs(self.directory, exist_ok=True)
        with _held(path):  # the lock is beside the folder: taken before it exists
            names.check_folder(self.directory, name)
            os.mkdir(path)  # FileExistsError: the pool has it
            session = Session(name, path=path, seed=seed)
            session.save()
            return session

    def _load(self, name: str, path: str) -> Session:
        names.check_folder(self.directory, name)
        if not os.path.isdir(path):
            raise FileNotFoundError(f"no session named {name!r} at {path}")
        return Session(name, path=path)

    def _prepare(self, name: str, path: str, session: Session | None, create: bool) -> Session:
        """Under the session lock (:class:`SessionBusyError` if held elsewhere):
        load the session of a name, and save one that has no ``session.json``
        (:class:`FileNotFoundError` instead without *create*)."""
        names.check_folder(self.directory, name)
        if not create and not os.path.isdir(path):
            raise FileNotFoundError(f"no session named {name!r} at {path}")
        with _held(path):
            names.check_folder(self.directory, name)  # a twin may have come meanwhile
            if session is None:
                session = Session(name, path=path)
            _ensure(name, path, session, create)
            return session


def _remove_graves(directory: str) -> None:
    for grave in names.graves(directory):
        shutil.rmtree(grave, ignore_errors=True)


def _ensure(name: str, path: str, session: Session, create: bool) -> None:
    """With the session lock held: *session* has its ``session.json``, saved
    now if missing and *create* (the folder too); else :class:`FileNotFoundError`,
    with nothing made."""
    if os.path.exists(os.path.join(path, _SESSION_FILE)):
        return
    if create:
        session.save()
        return
    raise FileNotFoundError(f"no session named {name!r} at {path}")


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
