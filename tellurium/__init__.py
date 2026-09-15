"""Tellurium automates browsers. Quietly."""

from tellurium.browser.browser import Browser
from tellurium.browser.cookie import Cookie
from tellurium.browser.element import Element
from tellurium.browser.tab import Tab
from tellurium.capture.intercept import InterceptedRequest
from tellurium.capture.request import CapturedRequest

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
    "__version__",
]
