"""Which client holds each named session: named sessions live on disk, shared by
every client of one server, but a profile takes one Chrome at a time."""

from __future__ import annotations

from tellurium.mcp.results import ToolError


class SessionClaims:
    """Names in use by an owner (a client's session pool), from before its
    browser starts until after it is closed and saved."""

    def __init__(self) -> None:
        self._owners: dict[str, object] = {}

    def take(self, name: str, owner: object) -> None:
        """Claim *name* for *owner*; a :class:`ToolError` if another owner has it."""
        holder = self._owners.setdefault(name, owner)
        if holder is not owner:
            raise ToolError(
                f"Session {name!r} is already open by another MCP client: close it "
                "there (or wait for its idle timeout), or open another name"
            )

    def release(self, name: str, owner: object) -> None:
        """Free *name*, if *owner* holds it."""
        if self._owners.get(name) is owner:
            del self._owners[name]
