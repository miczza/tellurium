"""Shared types for the CDP layer."""

from typing import Any

T_JSON_DICT = dict[str, Any]


class CDPError(Exception):
    """Error returned by Chrome in response to a CDP command."""

    def __init__(self, message: str, code: int | None = None):
        self.message = message
        self.code = code
        super().__init__(f"CDP error {code}: {message}" if code else message)


class TargetCrashedError(ConnectionError):
    """The target's renderer crashed: its commands can never be answered.

    A :class:`ConnectionError`, so code that already handles a closed
    session handles a crashed one too.
    """
