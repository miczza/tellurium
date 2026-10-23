"""JavaScript dialogs (alert, confirm, prompt, beforeunload) of one tab.

While a dialog is open Chrome answers no command on the page, so every tab
owns a :class:`DialogGuard` that answers each dialog: through the user's
``Tab.on_dialog`` handler when one is set, otherwise through the tab's policy.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Literal

from tellurium.cdp.types import CDPError

if TYPE_CHECKING:
    from tellurium.cdp.transport._session import Session

logger = logging.getLogger("tellurium")

DialogPolicy = Literal["dismiss", "accept", "manual"]
DIALOG_POLICIES: tuple[str, ...] = ("dismiss", "accept", "manual")
DialogHandler = Callable[["Dialog"], Awaitable[None] | None]

# Page.handleJavaScriptDialog is answered at once; the bound only guards a
# renderer that died with the dialog open.
_RESPOND_TIMEOUT = 5.0
# An on_dialog handler that has not decided by then yields to the policy.
HANDLER_TIMEOUT = 10.0


def check_policy(policy: str) -> str:
    if policy not in DIALOG_POLICIES:
        raise ValueError(f"Unknown dialogs policy {policy!r}; expected one of {DIALOG_POLICIES}")
    return policy


class Dialog:
    """A JavaScript dialog the page opened.

    ``type`` is ``"alert"``, ``"confirm"``, ``"prompt"`` or ``"beforeunload"``.
    Call :meth:`accept` or :meth:`dismiss` once; later calls do nothing.
    """

    def __init__(self, session: Session, params: dict):
        self._session = session
        self.type: str = params.get("type", "")
        self.message: str = params.get("message", "")
        self.default_prompt: str = params.get("defaultPrompt", "")
        self.url: str = params.get("url", "")
        self._handled = False

    @property
    def handled(self) -> bool:
        """True once :meth:`accept` or :meth:`dismiss` was called."""
        return self._handled

    async def accept(self, text: str | None = None) -> None:
        """Press OK; *text* is the answer of a ``prompt()``."""
        await self._respond(True, text)

    async def dismiss(self) -> None:
        """Press Cancel (``confirm()`` returns false, ``prompt()`` null)."""
        await self._respond(False, None)

    async def _respond(self, accept: bool, text: str | None) -> None:
        if self._handled:
            return
        self._handled = True
        params: dict = {"accept": accept}
        if text is not None:
            params["promptText"] = text
        try:
            await self._session.send(
                "Page.handleJavaScriptDialog", params, timeout=_RESPOND_TIMEOUT
            )
        except CDPError:
            # "No dialog is showing": a navigation or the page closed it.
            logger.debug("Dialog %r already closed", self.message, exc_info=True)

    def __repr__(self) -> str:
        return f"Dialog(type={self.type!r}, message={self.message!r})"


class DialogGuard:
    """Answers every dialog of one tab session so that none can freeze it.

    The handler runs first; a dialog it leaves undecided (or that it fails
    on, or that runs past ``handler_timeout``) gets the policy: ``"dismiss"`` (``beforeunload`` is accepted, so a
    navigation is never cancelled), ``"accept"``, or ``"manual"`` (left open
    for the caller).
    """

    def __init__(self, session: Session, policy: str = "dismiss"):
        self._session = session
        self._policy = check_policy(policy)
        self._handler: DialogHandler | None = None
        self._tasks: set[asyncio.Task] = set()
        self.last: Dialog | None = None
        self.handler_timeout = HANDLER_TIMEOUT
        session.on("Page.javascriptDialogOpening", self._on_opening)

    @property
    def policy(self) -> str:
        return self._policy

    @policy.setter
    def policy(self, value: str) -> None:
        self._policy = check_policy(value)

    def set_handler(self, handler: DialogHandler | None) -> None:
        self._handler = handler

    def _on_opening(self, params: dict) -> None:
        dialog = Dialog(self._session, params)
        self.last = dialog
        task = asyncio.get_running_loop().create_task(self._settle(dialog))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _settle(self, dialog: Dialog) -> None:
        handler = self._handler
        if handler is not None:
            try:
                result = handler(dialog)
                if inspect.isawaitable(result):
                    await asyncio.wait_for(result, timeout=self.handler_timeout)
            except asyncio.TimeoutError:
                logger.warning(
                    "on_dialog handler undecided after %ss: %r", self.handler_timeout, dialog
                )
            except Exception:  # noqa: BLE001 — the dialog must still be closed
                logger.exception("on_dialog handler failed for %r", dialog)
        if dialog.handled or self._policy == "manual":
            return
        try:
            if self._policy == "accept" or dialog.type == "beforeunload":
                await dialog.accept()
            else:
                await dialog.dismiss()
        except Exception:  # noqa: BLE001 — tab closing, nothing left to unblock
            logger.debug("Could not answer %r", dialog, exc_info=True)

    def close(self) -> None:
        """Stop answering dialogs and cancel any pending answer."""
        self._session.off("Page.javascriptDialogOpening", self._on_opening)
        for task in list(self._tasks):
            task.cancel()
