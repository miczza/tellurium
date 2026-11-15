"""The shadow copy (VSS, volsnap) events of a Windows runner, for the hang probe.

A shadow copy freezes the writes to the volume, and with them Chrome, for
~25 s (run 43429848268) and up to ~60 s (run 43496669198). Through
PowerShell the events were lost just when they mattered: the frozen runner did
not start it in 20 s. ``wevtutil`` is a small native program, asked with a
deadline of its own for each log; a log that timed out is asked again once
the rest of the report is made (:meth:`Events.read_missed`): the events of a
freeze are logged anyway, with their moment.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime

#: The logs that hold them: the VSS service writes to Application, the volsnap
#: driver to System.
LOGS = ("Application", "System")
#: Their sources.
PROVIDERS = (
    "VSS",
    "volsnap",
    "Volsnap",
    "Microsoft-Windows-VolumeSnapshot-Driver",
    "Microsoft-Windows-VSS",
)
#: Deadline of each ``wevtutil``.
TIMEOUT = 8.0
#: Events kept per log, the newest.
MAX_EVENTS = 20
#: Characters of an event's data kept.
MAX_DATA = 120

_EVENT = re.compile(r"<Event[ >].*?</Event>", re.S)
_PROVIDER = re.compile(r"<Provider Name='([^']*)'")
_ID = re.compile(r"<EventID[^>]*>(\d+)<")
_LEVEL = re.compile(r"<Level>(\d+)<")
_CHANNEL = re.compile(r"<Channel>([^<]*)<")
_WHEN = re.compile(r"<TimeCreated SystemTime='([^']*)'")
_DATA = re.compile(r"<Data(?: [^>]*)?>([^<]*)</Data>")

Run = Callable[..., tuple[str, bool]]


def command(log: str, window: float) -> list[str]:
    """``wevtutil`` for the shadow copy events of *log* of the last *window* s,
    newest first, as XML."""
    names = " or ".join(f"@Name='{name}'" for name in PROVIDERS)
    query = (
        f"*[System[Provider[{names}] and TimeCreated[timediff(@SystemTime) <= "
        f"{int(window * 1000)}]]]"
    )
    return ["wevtutil", "qe", log, f"/q:{query}", "/f:xml", "/rd:true", f"/c:{MAX_EVENTS}"]


def lines(xml: str) -> list[str]:
    """One line per event of *xml*, oldest first: log, source, id, level,
    moment (``at@<Unix ms>``) and the start of its data."""
    out = []
    for event in _EVENT.findall(xml):
        when = _WHEN.search(event)
        at = _unix_ms(when.group(1)) if when else None
        data = " ".join(d.strip() for d in _DATA.findall(event) if d.strip())[:MAX_DATA]
        out.append(
            (
                at or 0,
                f"  {_first(_CHANNEL, event)} {_first(_PROVIDER, event)} id={_first(_ID, event)}"
                f" level={_first(_LEVEL, event)} at@{at if at is not None else '?'} {data}".rstrip(),
            )
        )
    return [line for _, line in sorted(out, key=lambda pair: pair[0])]


class Events:
    """The shadow copy events of the last *window* seconds, log by log."""

    def __init__(self, window: float, run: Run | None = None) -> None:
        self.window = window
        self._run = run
        self._missed: list[str] = []

    def read(self) -> str:
        """Every log's events; a log that does not answer is noted as missed."""
        return self._read(LOGS)

    def read_missed(self) -> str:
        """The logs that did not answer :meth:`read`, asked once more; ``""``
        when none was missed."""
        if not self._missed:
            return ""
        missed, self._missed = self._missed, []
        return "shadow copy events, asked again:\n" + self._read(missed)

    def _read(self, logs) -> str:
        run = self._run or _default_run()
        out, found = [], []
        for log in logs:
            text, ok = run(command(log, self.window), timeout=TIMEOUT)
            if not ok:
                self._missed.append(log)
                out.append(f"  {log}: {text.strip()[:200]}")
                continue
            found.extend(lines(text))
        found.sort(key=_moment)
        out.extend(found)
        return "\n".join(out or ["  (none)"])


def _moment(line: str) -> int:
    match = re.search(r"at@(\d+)", line)
    return int(match.group(1)) if match else 0


def _unix_ms(text: str) -> int | None:
    """``2026-11-13T10:00:01.5000000Z`` as Unix ms (Windows gives 7 digits)."""
    match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?Z?", text.strip())
    if not match:
        return None
    whole = datetime.strptime(match.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    fraction = float(f"0.{match.group(2) or 0}")
    return int(round((whole.timestamp() + fraction) * 1000))


def _first(pattern: re.Pattern, text: str) -> str:
    match = pattern.search(text)
    return match.group(1) if match else "?"


def _default_run() -> Run:
    from tests.process_snapshot import _run  # its deadline ends every process it started

    return _run


__all__ = ["Events", "command", "lines"]
