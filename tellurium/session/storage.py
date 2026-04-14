"""I/O for session.json — stateless, atomic writes."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from tellurium import __version__ as _tellurium_version
from tellurium.session.errors import SessionCorruptError


def save(path: str, data: dict[str, Any], full: bool) -> None:
    """Write session data to `path` atomically.

    When `full=False`, the `launch` key is stripped before writing.
    `updated_at` is set automatically. `tellurium_version` is stamped.
    The file is created with mode 0600 on POSIX.
    """
    out = dict(data)
    out["tellurium_version"] = _tellurium_version
    out["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not full:
        out.pop("launch", None)

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)

    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)
    if sys.platform != "win32":
        os.chmod(path, 0o600)
