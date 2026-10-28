"""Whether ``tellurium mcp`` and ``tellurium login`` open a session with stealth.

They launch with ``stealth=True``; a session saved with its own
``--user-agent`` among its launch args cannot be (stealth gives the User-Agent
one source, the profile, and refuses the flag), and neither command lets one
pass ``stealth=False``. Such a session is opened without stealth: its own
User-Agent is the identity it was made with. :func:`notice` is what the
person is told (the MCP reply, ``tellurium login``'s stderr).
"""

from __future__ import annotations

from typing import Any


def notice(session: Any) -> str | None:
    """Why *session* is opened without stealth, or ``None`` if it is not."""
    from tellurium.stealth.engine import refuse_user_agent_arg

    try:
        refuse_user_agent_arg((getattr(session, "_launch_hints", None) or {}).get("args"))
    except ValueError:
        return (
            f"session {session.name!r} sets its own --user-agent in its saved launch args: "
            "opened without stealth (no stealth profile, no fingerprint patches)"
        )
    return None
