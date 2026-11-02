"""Session class — coordinator for persistent browser state and login flow."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import secrets
import threading
import warnings
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from tellurium.session import manual_login, profile_release, session_cookies, storage
from tellurium.session.errors import (
    SessionBusyError,
    SessionInvalidError,
    SessionLoginFailedError,
)
from tellurium.session.lock import SessionLock
from tellurium.session.validators import combine as _combine_validators

_VALID_MODES = ("all", "any")
_LOGIN_FAILURE_POLICIES = ("raise", "manual")
#: Seconds a person gets to sign in with ``on_login_failure="manual"``.
MANUAL_TIMEOUT = 600.0
#: Bound on a :meth:`Session.save` from another thread waiting for Chrome's jar.
LIVE_SAVE_TIMEOUT = 2 * session_cookies.TIMEOUT

logger = logging.getLogger(__name__)


class Session:
    def __init__(
        self,
        name: str,
        *,
        path: str | None = None,
        seed: int | None = None,
        validate_mode: str = "all",
    ) -> None:
        if validate_mode not in _VALID_MODES:
            raise ValueError(
                f"validate_mode must be one of {_VALID_MODES!r}, got {validate_mode!r}"
            )

        self.name = name
        self.path = (
            os.path.abspath(path) if path else os.path.abspath(os.path.join("sessions", name))
        )
        self.validate_mode = validate_mode
        self._validators: list = []
        self._login = None  # type: ignore[assignment]
        self._launch_hints: dict[str, Any] = {}
        self._last_launch_params: dict[str, Any] | None = None
        self._started = False
        self._created_at: str | None = None
        self._chromium_version_used: str | None = None  # set by Browser.launch/Session.start
        self._chromium_version_loaded: str | None = None
        # The cookie jar as of the last start or close (None: unknown).
        self._session_cookies: list | None = None
        # Whether _session_cookies is the jar Chrome had as it closed.
        self._cookies_at_close = False
        # The saved cookies the running start puts back (None: no start yet).
        self._reinjection: session_cookies.Reinjection | None = None
        # Run in a thread once start holds the lock, before Chrome (SessionPool).
        self._on_lock: Any = None
        # The Chrome of the running start (None between starts), its loop,
        # and the live save under way.
        self._live: Any = None
        self._live_loop: asyncio.AbstractEventLoop | None = None
        self._saving: asyncio.Task | None = None
        # Writes of cookies.json during a start: one at a time, and none from
        # a live save begun before the close's (its epoch is then stale).
        self._jar_lock = threading.Lock()
        self._jar_epoch = 0

        loaded = storage.load(self._json_path())
        if loaded is None:
            # Fresh session
            self.seed = seed if seed is not None else _fresh_seed()
            self.metadata: dict[str, Any] = {}
        else:
            # File wins: constructor seed is ignored
            self.seed = (
                int(loaded["seed"])
                if "seed" in loaded
                else (seed if seed is not None else _fresh_seed())
            )
            self.metadata = dict(loaded.get("metadata", {}))
            if "launch" in loaded and isinstance(loaded["launch"], dict):
                self._launch_hints = dict(loaded["launch"])
            self._created_at = loaded.get("created_at")
            self._chromium_version_loaded = loaded.get("chromium_version") or None

    def _json_path(self) -> str:
        return os.path.join(self.path, "session.json")

    @property
    def chromium_version(self) -> str | None:
        """The Chromium version locked to this session (if any).

        Returns the value set by the most recent start()/launch or the one
        persisted to session.json, whichever is present. Used-at-launch wins
        over loaded-from-disk because it reflects the live state.
        """
        return self._chromium_version_used or self._chromium_version_loaded

    def get(self, key: str, default: Any = None) -> Any:
        return self.metadata.get(key, default)

    def add(self, key: str, value: Any) -> None:
        """Set metadata[key] = value only if key is not present."""
        if key in self.metadata:
            return
        _validate_json_value(value)
        self.metadata[key] = value

    def set(self, key: str, value: Any) -> None:
        """Set metadata[key] = value, overwriting any existing value."""
        _validate_json_value(value)
        self.metadata[key] = value

    def validate(self, fn):
        """Decorator: register `fn` as a session validator.

        The callback must be async and accept `(tab)`. It should return a truthy
        value if the session is considered valid. Raising is treated as invalid
        in "all" mode, and as skipped-try-next in "any" mode.
        """
        self._validators.append(fn)
        return fn

    def login(self, fn):
        """Decorator: register `fn` as the login callback.

        The callback must be async and accept `(tab, metadata)`. It is invoked
        when validation fails. Only one login can be registered — calling this
        decorator twice replaces the previous one with a warning.
        """
        if self._login is not None:
            warnings.warn(
                "@session.login called twice; replacing the previous callback",
                stacklevel=2,
            )
        self._login = fn
        return fn

    def save(self, *, full: bool = False) -> None:
        """Serialize the current session state to session.json, and the cookie
        jar to cookies.json: the one of the last start or close, or, during a
        start, the jar Chrome has now.

        During a start, on its own loop, use ``await session.save_now()``:
        ``save()`` cannot wait for Chrome there and raises ``RuntimeError``
        (an old jar would be wrong). From another thread
        (``await asyncio.to_thread(session.save)``) it waits for Chrome, at
        most :data:`LIVE_SAVE_TIMEOUT` seconds. A Chrome that does not answer
        leaves cookies.json as it was, with a warning in the log.

        `full=True` includes the last set of launch parameters used by start()
        (or stored hints if start() has not run). If neither exists, the file
        is still lean (no `launch` block).
        """
        # Taken before anything else: a close that comes during this save
        # makes it stale, however long the session.json write takes.
        browser, loop, epoch = self._live, self._live_loop, self._jar_epoch
        if browser is not None and _running_loop() is loop:
            raise RuntimeError(
                "session.save() on the loop of a running start cannot read Chrome's "
                "cookies: use `await session.save_now()`"
            )
        self._write_json(full)
        if browser is None or loop is None:
            self._write_known_jar()
            return
        future = asyncio.run_coroutine_threadsafe(self._tracked_save(browser, epoch), loop)
        try:
            future.result(LIVE_SAVE_TIMEOUT)
        except Exception:  # noqa: BLE001 - the loop is stuck or gone: keep the file
            future.cancel()
            logger.warning("could not save the cookies of %s", self.path, exc_info=True)

    async def save_now(self, *, full: bool = False) -> None:
        """:meth:`save`, from async code: during a start the cookie jar is the
        one Chrome has now (read within ``session_cookies.TIMEOUT``; a Chrome
        that does not answer leaves cookies.json as it was, with a warning in
        the log), else the one of the last start or close."""
        browser, epoch = self._live, self._jar_epoch  # see save()
        if browser is not None and _running_loop() is not self._live_loop:
            raise RuntimeError(
                "session.save_now() must run on the loop of the running start; "
                "from another thread use session.save()"
            )
        await asyncio.to_thread(self._write_json, full)
        if browser is None:
            await asyncio.to_thread(self._write_known_jar)
            return
        self._saving = asyncio.ensure_future(self._save_live(browser, epoch))
        await self._saving

    def _write_json(self, full: bool) -> None:
        if self._created_at is None:
            self._created_at = datetime.now(UTC).isoformat(timespec="seconds")

        payload: dict[str, Any] = {
            "name": self.name,
            "seed": int(self.seed),
            "metadata": dict(self.metadata),
            "created_at": self._created_at,
        }

        cv = self.chromium_version
        if cv:
            payload["chromium_version"] = cv

        if full:
            launch = self._last_launch_params or self._launch_hints
            if launch:
                payload["launch"] = dict(launch)

        storage.save(self._json_path(), payload, full=full)

    def _write_known_jar(self) -> None:
        if self._session_cookies is not None:
            session_cookies.save(self.path, self._session_cookies, at_close=self._cookies_at_close)

    async def _tracked_save(self, browser, epoch: int) -> None:
        self._saving = asyncio.current_task()  # the close waits for it
        await self._save_live(browser, epoch)

    async def _save_live(self, browser, epoch: int) -> None:
        """Chrome's jar now (with the cookies a restore left pending), not as
        it closes: the next start only puts back what Chrome lacks. Cancelled
        mid-write, the write may still end, but never after the close's:
        *epoch* is the one the save began at."""
        try:
            jar = await session_cookies.snapshot(browser)
            assert self._reinjection is not None  # set before _live
            cookies = self._reinjection.keep(jar)
            wrote = await asyncio.to_thread(self._write_jar, cookies, epoch=epoch)
        except Exception:  # noqa: BLE001 - Chrome gone or hung: keep the file
            logger.warning("could not save the cookies of %s", self.path, exc_info=True)
            return
        if wrote:
            self._session_cookies, self._cookies_at_close = cookies, False

    def _write_jar(self, cookies: list, *, epoch: int | None = None) -> bool:
        """Write *cookies* to cookies.json, one writer at a time: the close's
        (*epoch* ``None``: saved at close, and from then on the live saves
        begun before it are stale), or a live save's begun at *epoch*, skipped
        (``False``) if the close has come since."""
        with self._jar_lock:
            if epoch is None:
                self._jar_epoch += 1
            elif epoch != self._jar_epoch:
                return False
            session_cookies.save(self.path, cookies, at_close=epoch is None)
            return True

    def _seal_jar(self) -> None:
        """No live save writes from now on; one under way has ended."""
        with self._jar_lock:
            self._jar_epoch += 1

    @asynccontextmanager
    async def start(
        self,
        *,
        on_login_failure: str = "raise",
        manual_timeout: float = MANUAL_TIMEOUT,
        **kwargs,
    ):
        """Launch a browser bound to this session, run validators, and optionally
        execute the login callback if validation fails.

        *on_login_failure*: ``"raise"`` (default) raises when validation fails
        with no login callback, or the callback raises; ``"manual"`` hands the
        browser to a person instead: Chrome is reopened with a window if it was
        headless, a :meth:`Tab.wait_for_human` banner asks to sign in, and on
        "Done" the validators run again, until they pass
        (:class:`SessionLoginFailedError` after *manual_timeout* seconds, at once
        if there is no display for the window). There each round of the
        validators gets at most ``manual_login.VALIDATOR_TIMEOUT`` seconds (a
        hung one counts as not signed in). The yielded browser is then the
        headed one. All of it happens inside this start, under its lock.

        Yields the Browser instance. Closes it on exit. Never auto-saves
        session.json; the cookie jar is written to cookies.json before Chrome
        closes (on error too), and the cookies Chrome lost on the way (those
        with no expiry, the last one written) go back before the validators run.
        The session folder is locked from before Chrome starts until after it
        is closed, even on error or cancellation: another process (or another
        :class:`Session` on the same folder) gets :class:`SessionBusyError`.
        """
        if self._started:
            raise RuntimeError("session already started")
        if on_login_failure not in _LOGIN_FAILURE_POLICIES:
            raise ValueError(
                f"on_login_failure must be one of {_LOGIN_FAILURE_POLICIES!r}, "
                f"got {on_login_failure!r}"
            )
        if not manual_timeout > 0:
            raise ValueError(f"manual_timeout must be positive, got {manual_timeout!r}")

        merged = _merge_launch_params(kwargs, self._launch_hints)
        if self._chromium_version_loaded and "chromium_version" not in merged:
            merged["chromium_version"] = self._chromium_version_loaded

        # Lazy import to avoid top-level cycles
        from tellurium import Browser

        lock = SessionLock(self.path)
        await lock.acquire_async()  # creates the folder; non-blocking syscalls
        chrome_dir = os.path.join(self.path, "chrome")

        # Single try covers both Browser.launch failure (leak prevention) and
        # user-body / validation / login exceptions. Python runs finally when
        # an exception propagates through a generator frame, including the
        # pre-yield branch where validation/login can raise.
        browser = None
        self._reinjection = None
        try:
            if self._on_lock is not None:
                await asyncio.to_thread(self._on_lock)
            browser = await self._launch(Browser, chrome_dir, merged)
            # Only record params of a successful launch, so save(full=True)
            # after a failed start() does not persist a bad configuration.
            self._last_launch_params = dict(merged)
            # Persist-worthy: record the chromium_version we actually launched with.
            self._chromium_version_used = (
                merged.get("chromium_version") or self._chromium_version_used
            )
            self._started = True
            await self._restore_cookies(browser)
            self._live, self._live_loop = browser, asyncio.get_running_loop()
            manual = on_login_failure == "manual"
            if not await self._run_validation_and_login(browser, manual=manual):
                if merged.get("headless"):  # a person needs a window
                    manual_login.check_display(self.name)
                    closing, browser, self._live = browser, None, None
                    await self._close_browser(closing)
                    browser = await self._launch(Browser, chrome_dir, {**merged, "headless": False})
                    await self._restore_cookies(browser)
                    self._live = browser
                await manual_login.sign_in(
                    browser, self.name, self._validators, self.validate_mode, manual_timeout
                )
            yield browser
        finally:
            self._started = False
            self._live = None
            try:
                if browser is not None:
                    await self._close_browser(browser)
            finally:
                lock.release()  # last: after Chrome has let go of the profile

    async def _launch(self, browser_cls, chrome_dir: str, params: dict):
        chrome_pid = await profile_release.wait(chrome_dir)  # a dead holder's Chrome
        if chrome_pid is not None:
            raise SessionBusyError(self.path, chrome_pid)
        return await browser_cls.launch(user_data_dir=chrome_dir, seed=int(self.seed), **params)

    async def _restore_cookies(self, browser) -> None:
        saved, at_close = await asyncio.to_thread(session_cookies.read, self.path)
        self._session_cookies, self._cookies_at_close = saved, False
        # Set before the next await: a cancelled restore leaves it pending.
        self._reinjection = session_cookies.Reinjection(saved, saved_wins=at_close)
        if saved:  # a run under way: if it never closes, Chrome's copy is the newer
            try:
                await asyncio.to_thread(session_cookies.save, self.path, saved, at_close=False)
            except OSError:
                logger.warning("could not mark the cookies of %s", self.path, exc_info=True)
        try:
            await self._reinjection.run(browser)
        except Exception:  # noqa: BLE001 - the validators judge the session
            logger.warning("could not restore the cookies of %s", self.path, exc_info=True)

    async def _close_browser(self, browser) -> None:
        """Keep the cookie jar, then close Chrome (that even if the
        first step fails or is cancelled). Not before the start has read
        cookies.json: Chrome's jar lacks the cookies it holds, so writing it
        would lose them."""
        try:
            saving = self._saving
            if saving is not None and not saving.done():  # a live save writes first
                await asyncio.gather(saving, return_exceptions=True)
            if self._reinjection is None:
                return  # the finally still closes Chrome
            cookies = self._reinjection.keep(await session_cookies.snapshot(browser))
            await asyncio.to_thread(self._write_jar, cookies)
            self._session_cookies, self._cookies_at_close = cookies, True
        except Exception:  # noqa: BLE001 - Chrome gone: keep the previous file
            logger.warning("could not save the cookies of %s", self.path, exc_info=True)
        finally:
            if self._reinjection is not None:
                self._reinjection.drop()
            self._jar_epoch += 1  # a live save that has not written yet never will
            try:
                await asyncio.to_thread(self._seal_jar)  # and one writing has ended
            finally:
                try:
                    await browser.close()
                except Exception:  # noqa: BLE001 - cleanup after failure
                    pass

    async def _run_validation_and_login(self, browser, *, manual: bool) -> bool:
        """Whether the session is good (no validators, they pass, or the login
        callback went through); False, instead of raising, only when *manual*."""
        if not self._validators:
            return True
        tab = browser.main_tab
        if manual:  # bounded: a hung validator hands over to the person
            timeout = manual_login.VALIDATOR_TIMEOUT
            ok = await manual_login.signed_in(self._validators, self.validate_mode, tab, timeout)
        else:
            ok = await _combine_validators(self._validators, self.validate_mode, tab=tab)
        if ok:
            return True
        # Validation failed
        if self._login is None:
            if manual:
                return False
            raise SessionInvalidError(
                "session validation failed and no @session.login is registered"
            )
        try:
            await self._login(tab, self.metadata)
        except Exception as exc:
            if manual:
                logger.warning("login callback of %s raised", self.path, exc_info=True)
                return False
            raise SessionLoginFailedError("login callback raised") from exc
        return True


_MANAGED_LAUNCH_KEYS = frozenset({"user_data_dir", "seed"})


def _merge_launch_params(kwargs: dict, hints: dict) -> dict:
    """Merge explicit kwargs with stored hints. kwargs wins per-key.

    Raises TypeError if the caller passes keys managed by Session itself
    (user_data_dir, seed). Managed keys in `hints` are silently dropped
    (defensive, in case an older file contains them).
    """
    bad = _MANAGED_LAUNCH_KEYS & kwargs.keys()
    if bad:
        raise TypeError(f"session.start() manages these parameters internally: {sorted(bad)}")
    safe_hints = {k: v for k, v in hints.items() if k not in _MANAGED_LAUNCH_KEYS}
    return {**safe_hints, **kwargs}


def _validate_json_value(value: Any) -> None:
    """Raise TypeError if value (or any nested element) is not JSON-serializable."""
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(
                f"metadata float values must be finite (got {value!r}); "
                "NaN and Infinity are not valid JSON"
            )
        return
    if isinstance(value, list):
        for v in value:
            _validate_json_value(v)
        return
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(f"metadata dict keys must be str, got {type(k).__name__}")
            _validate_json_value(v)
        return
    raise TypeError(
        f"metadata values must be JSON-serializable "
        f"(str, int, float, bool, None, list, dict); got {type(value).__name__}"
    )


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _fresh_seed() -> int:
    # Not the global `random`: a script that seeds it would give every identity one fingerprint.
    return secrets.randbelow(0xFFFFFFFF) + 1
