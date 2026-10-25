"""How many browsers the server may run at once, across all its clients: each
is a Chrome, and an HTTP server must not let its clients exhaust the machine."""

from __future__ import annotations

from tellurium.mcp.results import ToolError


class SessionBudget:
    """*total* places, one per session open or launching."""

    def __init__(self, total: int | None):
        self.total = total
        self.used = 0

    def take(self) -> None:
        """Take a place; a :class:`ToolError` if they are all in use."""
        if self.total is not None and self.used >= self.total:
            raise ToolError(
                f"The server already runs {self.total} sessions, the most it allows: "
                "close one of yours with session-close, or try again later"
            )
        self.used += 1

    def release(self) -> None:
        self.used = max(0, self.used - 1)
