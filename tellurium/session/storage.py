"""I/O for session.json — stateless, atomic writes."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

from tellurium import __version__ as _tellurium_version
from tellurium.session.errors import SessionCorruptError

#: On Windows a file being renamed over, or open while another rename lands,
#: refuses access for a moment: how long a write or a read keeps trying.
SHARING_PATIENCE = 2.0
_T = TypeVar("_T")

_KNOWN_FIELDS = frozenset(
    {
        "tellurium_version",
        "name",
        "seed",
        "metadata",
        "launch",
        "created_at",
        "updated_at",
        "chromium_version",
    }
)


def save(path: str, data: dict[str, Any], full: bool) -> None:
    """Write session data to `path` atomically.

    When `full=False`, the `launch` key is stripped before writing.
    `updated_at` is set automatically. `tellurium_version` is stamped.
    The file is created with mode 0600 on POSIX.
    """
    out = dict(data)
    out["tellurium_version"] = _tellurium_version
    out["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    if not full:
        out.pop("launch", None)

    write_private(path, out)


def write_private(path: str, data: Any) -> None:
    """Write *data* as JSON to *path* atomically (a temporary file of its own
    in the same folder, fsync, rename), mode 0600 on POSIX: concurrent writers
    never mix their bytes, the last rename wins whole."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)

    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:  # mkstemp: 0600 already
            json.dump(data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        _shared(lambda: os.replace(tmp, path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if sys.platform != "win32":
        os.chmod(path, 0o600)


def read_bytes(path: str) -> bytes:
    """The content of *path*, tried again for a moment on Windows while another
    writer's rename lands on it."""

    def read() -> bytes:
        with open(path, "rb") as f:
            return f.read()

    return _shared(read)


def read_text(path: str) -> str:
    """:func:`read_bytes`, as UTF-8 text."""
    return read_bytes(path).decode("utf-8")


def _shared(call: Callable[[], _T]) -> _T:
    """*call*, again for up to :data:`SHARING_PATIENCE` seconds while Windows
    refuses access (a file another thread or process renames or reads)."""
    deadline = time.monotonic() + SHARING_PATIENCE
    while True:
        try:
            return call()
        except PermissionError:
            if sys.platform != "win32" or time.monotonic() >= deadline:
                raise
        time.sleep(0.005)


def load(path: str) -> dict[str, Any] | None:
    """Read session.json at `path`. Returns None if the file does not exist.

    Raises SessionCorruptError if the file is present but cannot be parsed
    as a JSON object. Unknown top-level fields emit a warning and are dropped.
    """
    try:
        raw = json.loads(read_text(path))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as exc:
        raise SessionCorruptError(f"cannot parse session file at {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise SessionCorruptError(f"session file at {path} is not a JSON object")

    unknown = set(raw.keys()) - _KNOWN_FIELDS
    if unknown:
        warnings.warn(
            f"session.json contains unknown fields that will be dropped: {sorted(unknown)}",
            stacklevel=2,
        )

    return {k: v for k, v in raw.items() if k in _KNOWN_FIELDS}
