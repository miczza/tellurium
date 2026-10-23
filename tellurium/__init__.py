"""Tellurium automates browsers. Quietly."""

from tellurium.browser.browser import Browser
from tellurium.browser.cookie import Cookie
from tellurium.browser.dialog import Dialog
from tellurium.browser.element import Element
from tellurium.browser.handles import StaleElementError
from tellurium.browser.launcher import LaunchError
from tellurium.browser.navigation import NavigationError, NavigationTimeoutError
from tellurium.browser.tab import Tab
from tellurium.capture.intercept import InterceptedRequest
from tellurium.capture.request import CapturedRequest
from tellurium.cdp.types import TargetCrashedError

__version__ = "0.1.0"

from tellurium.session import Session  # noqa: E402 — after __version__ to avoid circular import

__all__ = [
    "Browser",
    "Cookie",
    "Tab",
    "Element",
    "CapturedRequest",
    "InterceptedRequest",
    "Session",
    "Dialog",
    "LaunchError",
    "NavigationError",
    "NavigationTimeoutError",
    "StaleElementError",
    "TargetCrashedError",
    "__version__",
]
