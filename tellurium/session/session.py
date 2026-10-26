"""Session class — coordinator for persistent browser state and login flow."""

from __future__ import annotations

import math
import os
import random
import warnings
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from tellurium.session import storage
from tellurium.session.errors import (
    SessionInvalidError,
    SessionLoginFailedError,
)
from tellurium.session.lock import SessionLock

_VALID_MODES = ("all", "any")


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

        loaded = storage.load(self._json_path())
        if loaded is None:
            # Fresh session
            self.seed = seed if seed is not None else random.randint(1, 0xFFFFFFFF)
            self.metadata: dict[str, Any] = {}
        else:
            # File wins: constructor seed is ignored
            self.seed = (
                int(loaded["seed"])
                if "seed" in loaded
                else (seed if seed is not None else random.randint(1, 0xFFFFFFFF))
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
        """Serialize the current session state to session.json.

        `full=True` includes the last set of launch parameters used by start()
        (or stored hints if start() has not run). If neither exists, the file
        is still lean (no `launch` block).
        """
        if self._created_at is None:
            self._created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

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

    @asynccontextmanager
    async def start(self, **kwargs):
        """Launch a browser bound to this session, run validators, and optionally
        execute the login callback if validation fails.

        Yields the Browser instance. Closes it on exit. Never auto-saves.
        The session folder is locked from before Chrome starts until after it
        is closed, even on error or cancellation: another process (or another
        :class:`Session` on the same folder) gets :class:`SessionBusyError`.
        """
        if self._started:
            raise RuntimeError("session already started")

        merged = _merge_launch_params(kwargs, self._launch_hints)
        if self._chromium_version_loaded and "chromium_version" not in merged:
            merged["chromium_version"] = self._chromium_version_loaded

        # Lazy import to avoid top-level cycles
        from tellurium import Browser

        lock = SessionLock(self.path)
        lock.acquire()  # creates the folder; a non-blocking syscall
        chrome_dir = os.path.join(self.path, "chrome")

        # Single try covers both Browser.launch failure (leak prevention) and
        # user-body / validation / login exceptions. Python runs finally when
        # an exception propagates through a generator frame, including the
        # pre-yield branch where validation/login can raise.
        browser = None
        try:
            browser = await Browser.launch(
                user_data_dir=chrome_dir,
                seed=int(self.seed),
                **merged,
            )
            # Only record params of a successful launch, so save(full=True)
            # after a failed start() does not persist a bad configuration.
            self._last_launch_params = dict(merged)
            # Persist-worthy: record the chromium_version we actually launched with.
            self._chromium_version_used = (
                merged.get("chromium_version") or self._chromium_version_used
            )
            self._started = True
            await self._run_validation_and_login(browser)
            yield browser
        finally:
            self._started = False
            try:
                if browser is not None:
                    try:
                        await browser.close()
                    except Exception:  # noqa: BLE001 - cleanup after failure
                        pass
            finally:
                lock.release()  # last: after Chrome has let go of the profile

    async def _run_validation_and_login(self, browser) -> None:
        if not self._validators:
            return
        tab = browser.main_tab
        ok = await _combine_validators(self._validators, self.validate_mode, tab=tab)
        if ok:
            return
        # Validation failed
        if self._login is None:
            raise SessionInvalidError(
                "session validation failed and no @session.login is registered"
            )
        try:
            await self._login(tab, self.metadata)
        except Exception as exc:
            raise SessionLoginFailedError("login callback raised") from exc


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


async def _combine_validators(validators, mode: str, *, tab) -> bool:
    """Run validators sequentially with short-circuit semantics.

    - "all": first falsy or raising validator wins (returns False).
    - "any": first truthy validator wins (returns True); raises are skipped.
    Returns the final boolean outcome.
    """
    if not validators:
        return True

    if mode == "all":
        for v in validators:
            try:
                result = await v(tab)
            except Exception:  # noqa: BLE001 - user validator errors mean invalid
                return False
            if not result:
                return False
        return True

    if mode == "any":
        for v in validators:
            try:
                result = await v(tab)
            except Exception:  # noqa: BLE001 - user validator errors are skipped
                continue
            if result:
                return True
        return False

    raise ValueError(f"unknown mode: {mode!r}")


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
