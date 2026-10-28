"""A person signs in to a session: ``Session.start(on_login_failure="manual")``.

A :meth:`Tab.wait_for_human` banner asks to sign in; on "Done" the validators
run again, until they pass or the start's *manual_timeout* runs out. A
validator that hangs is not left to stall it: each round gets at most
:data:`VALIDATOR_TIMEOUT` seconds and then counts as not signed in (the banner
comes back). Chrome needs a window for this: without a display the start
fails at once with an error that says so, before a headed Chrome is tried.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from tellurium.session.errors import SessionLoginFailedError
from tellurium.session.validators import combine

#: Bound on one round of the validators while a person signs in.
VALIDATOR_TIMEOUT = 30.0


def has_display() -> bool:
    """Whether a window can be shown: always on Windows and macOS, else an
    X11 (``DISPLAY``) or Wayland (``WAYLAND_DISPLAY``) display must be set."""
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def check_display(name: str) -> None:
    """:class:`SessionLoginFailedError` naming the display when there is none."""
    if not has_display():
        raise SessionLoginFailedError(
            f"session {name!r} needs a person to sign in, but there is no display "
            "(DISPLAY and WAYLAND_DISPLAY are unset) to open a browser window on"
        )


async def signed_in(validators: list, mode: str, tab: Any, timeout: float) -> bool:
    """The validators' verdict within *timeout* (and :data:`VALIDATOR_TIMEOUT`);
    ``False`` if they take longer."""
    try:
        return await asyncio.wait_for(
            combine(validators, mode, tab=tab), min(timeout, VALIDATOR_TIMEOUT)
        )
    except asyncio.TimeoutError:
        return False


async def sign_in(browser: Any, name: str, validators: list, mode: str, timeout: float) -> None:
    """A banner until "Done" and validators that pass, within *timeout*
    seconds (:class:`SessionLoginFailedError` after it)."""
    from tellurium.browser import human

    reason = f"Sign in to continue (session {name!r}), then click Done."
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    failure = SessionLoginFailedError(f"nobody signed in to session {name!r} within {timeout:g} s")
    while True:
        try:
            await human.wait_for_human(
                browser.main_tab, reason, timeout=max(deadline - loop.time(), 0)
            )
        except TimeoutError as exc:
            raise failure from exc
        left = deadline - loop.time()
        if left > 0 and await signed_in(validators, mode, browser.main_tab, left):
            return
        if deadline - loop.time() <= 0:
            raise failure
        reason = f"Still not signed in (session {name!r}): sign in, then click Done."
