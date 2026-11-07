"""What a ``tellurium login`` saw while its windows closed, for the message of
a test that lost a cookie: each jar read (and whether it held the cookie),
each target list, what the windows' watcher returned, in order and in ms."""

from __future__ import annotations

import time

from tellurium.session import login_command, session_cookies


class LoginTimeline:
    def __init__(self, monkeypatch, cookie: str) -> None:
        self.cookie = cookie
        self.keeper: str | None = None
        self._start = time.monotonic()
        self._events: list[str] = []
        real_snapshot = session_cookies.snapshot
        real_pages = login_command._pages
        real_windows_closed = login_command._windows_closed

        async def snapshot(browser):
            try:
                jar = await real_snapshot(browser)
            except BaseException as exc:
                self.note(f"jar read failed: {exc!r}")
                raise
            self.note(f"jar read, {cookie} {'in' if self._has(jar) else 'MISSING'}")
            return jar

        async def pages(root):
            found = await real_pages(root)
            self.note(f"pages {sorted(self._name(t) for t in found)}")
            return found

        async def windows_closed(browser, keeper):
            self.keeper = keeper
            result = await real_windows_closed(browser, keeper)
            shown = (
                "None"
                if result is None
                else f"jar, {cookie} {'in' if self._has(result) else 'MISSING'}"
            )
            self.note(f"windows watcher returned {shown}")
            return result

        monkeypatch.setattr(session_cookies, "snapshot", snapshot)
        monkeypatch.setattr(login_command, "_pages", pages)
        monkeypatch.setattr(login_command, "_windows_closed", windows_closed)

    def note(self, what: str) -> None:
        self._events.append(f"{(time.monotonic() - self._start) * 1000:8.0f} ms  {what}")

    def _has(self, jar) -> bool:
        return any(c.name == self.cookie for c in jar)

    def _name(self, target_id: str) -> str:
        return "keeper" if target_id == self.keeper else target_id[:6]

    def __str__(self) -> str:
        return "login timeline:\n" + "\n".join(self._events[-40:])

    __repr__ = __str__  # what pytest shows of an assertion's message
