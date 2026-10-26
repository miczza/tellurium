"""Which client holds each named session: named sessions live on disk, shared by
every client of one server, but a profile takes one Chrome at a time.

Across processes the session folder's lock (:class:`tellurium.session.lock.SessionLock`)
is what keeps a profile to one Chrome; the claims check it early, so the agent
hears which process has the session before any launch is tried.
"""

from __future__ import annotations

from tellurium.mcp.results import ToolError
from tellurium.session.lock import SessionLock


class SessionClaims:
    """Names in use by an owner (a client's session pool), from before its
    browser starts until after it is closed and saved."""

    def __init__(self) -> None:
        self._owners: dict[str, object] = {}

    def take(self, name: str, owner: object, path: str | None = None) -> None:
        """Claim *name* for *owner*; a :class:`ToolError` if another owner has it
        or, when *path* (its folder) is given, if another process has it open."""
        holder = self._owners.setdefault(name, owner)
        if holder is not owner:
            raise ToolError(
                f"Session {name!r} is already open by another MCP client: close it "
                "there (or wait for its idle timeout), or open another name"
            )
        if path is None:
            return
        pid = SessionLock.holder(path)  # a non-blocking probe of a tiny file
        if pid is not None:
            self.release(name, owner)
            raise busy(name, pid)

    def release(self, name: str, owner: object) -> None:
        """Free *name*, if *owner* holds it."""
        if self._owners.get(name) is owner:
            del self._owners[name]


def busy(name: str, pid: int | None) -> ToolError:
    """The error for a session another process (*pid*, if known) has open."""
    who = f"another process (PID {pid})" if pid else "another process"
    return ToolError(
        f"Session {name!r} is open in {who}: a CLI, a script or another server. "
        "Close it there, or open another name"
    )
