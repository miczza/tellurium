"""Session names that mean one folder on every system.

A pool moves from one system to another, so a name is checked against the
strictest of them: 1-64 letters, digits, ``.``, ``_`` or ``-``, starting with
a letter or digit (it never leaves the pool directory), not one of the names
Windows reserves for devices (``CON``, ``nul.txt``, ...), not ending with a
dot (Windows drops it), and not equal to another identity's name but for
case (one folder on a case-insensitive file system).
"""

from __future__ import annotations

import os
import re

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
#: Windows devices: a file named so, with any extension, is the device.
_RESERVED = frozenset(
    ["con", "prn", "aux", "nul"] + [f"{port}{n}" for port in ("com", "lpt") for n in range(1, 10)]
)
#: What :meth:`SessionPool.delete` moves a folder to before removing it.
_GRAVE = re.compile(r"\.(?P<name>.+)\.deleted-[0-9a-f]{32}")


def is_valid(name: object) -> bool:
    """Whether *name* is a portable session name (see the module)."""
    return (
        isinstance(name, str)
        and _NAME.fullmatch(name) is not None
        and not name.endswith(".")
        and name.split(".", 1)[0].casefold() not in _RESERVED
    )


def check(name: object) -> str:
    """*name*, or :class:`ValueError` if it is not portable."""
    if not is_valid(name):
        raise ValueError(
            f"invalid session name {name!r}: 1-64 letters, digits, '.', '_' or '-', "
            "starting with a letter or digit, not ending with '.', and not a name "
            "Windows reserves (CON, PRN, AUX, NUL, COM1-9, LPT1-9)"
        )
    return name  # type: ignore[return-value]


def check_folder(directory: str, name: str) -> None:
    """:class:`ValueError` if *name* in *directory* is a symlink, or another
    identity there has the same name but for case. Blocking: from a thread."""
    path = os.path.join(directory, name)
    if os.path.islink(path):
        raise ValueError(
            f"session {name!r} at {path} is a symlink: a session folder must be a real "
            "folder of the pool (remove the link, or open the session where it points)"
        )
    wanted = name.casefold()
    try:
        entries = os.scandir(directory)
    except FileNotFoundError:
        return
    with entries:
        for entry in entries:
            if entry.name != name and entry.name.casefold() == wanted and is_valid(entry.name):
                raise ValueError(
                    f"session name {name!r} differs only by case from {entry.name!r}, "
                    f"already in {directory}: on Windows and macOS they are one folder"
                )


def graves(directory: str) -> list[str]:
    """The folders an interrupted delete left in *directory*. Blocking."""
    try:
        entries = os.scandir(directory)
    except FileNotFoundError:
        return []
    with entries:
        return [
            entry.path
            for entry in entries
            if _GRAVE.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False)
        ]


def grave_name(name: str, token: str) -> str:
    """The name *name*'s folder takes while :meth:`SessionPool.delete` removes it."""
    return f".{name}.deleted-{token}"
