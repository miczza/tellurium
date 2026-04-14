"""Session class — coordinator for persistent browser state and login flow."""

from __future__ import annotations

import os
import random
from typing import Any

from tellurium.session import storage
from tellurium.session.errors import SessionCorruptError

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
        self.path = os.path.abspath(path) if path else os.path.abspath(
            os.path.join("sessions", name)
        )
        self.validate_mode = validate_mode
        self._validators: list = []
        self._login = None  # type: ignore[assignment]
        self._launch_hints: dict[str, Any] = {}
        self._last_launch_params: dict[str, Any] | None = None
        self._started = False
        self._created_at: str | None = None

        loaded = storage.load(self._json_path())
        if loaded is None:
            # Fresh session
            self.seed = seed if seed is not None else random.randint(1, 0xFFFFFFFF)
            self.metadata: dict[str, Any] = {}
        else:
            # File wins: constructor seed is ignored
            self.seed = int(loaded["seed"]) if "seed" in loaded else (
                seed if seed is not None else random.randint(1, 0xFFFFFFFF)
            )
            self.metadata = dict(loaded.get("metadata", {}))
            if "launch" in loaded and isinstance(loaded["launch"], dict):
                self._launch_hints = dict(loaded["launch"])
            self._created_at = loaded.get("created_at")

    def _json_path(self) -> str:
        return os.path.join(self.path, "session.json")

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


def _validate_json_value(value: Any) -> None:
    """Raise TypeError if value (or any nested element) is not JSON-serializable."""
    if value is None or isinstance(value, (str, int, float, bool)):
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
