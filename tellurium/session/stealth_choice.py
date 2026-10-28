"""Whether ``tellurium mcp`` and ``tellurium login`` open a session with stealth.

They launch with ``stealth=True``; a session saved with its own
``--user-agent`` among its launch args cannot be (stealth gives the User-Agent
one source, the profile, and refuses the flag), and neither command lets one
pass ``stealth=False``. Such a session is opened without stealth: its own
User-Agent is the identity it was made with.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def stealth_for(session: Any) -> bool:
    """``True``, unless the stored launch args of *session* set a User-Agent."""
    from tellurium.stealth.engine import refuse_user_agent_arg

    try:
        refuse_user_agent_arg(session._launch_hints.get("args"))
    except ValueError:
        logger.warning("session %s sets its own --user-agent: opened without stealth", session.path)
        return False
    return True
