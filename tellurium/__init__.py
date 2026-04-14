"""Tellurium automates browsers. Quietly."""
from tellurium.browser.browser import Browser
from tellurium.browser.cookie import Cookie

__version__ = "0.1.0"

from tellurium.session import Session  # noqa: E402 — after __version__ to avoid circular import

__all__ = ["Browser", "Cookie", "Session"]
