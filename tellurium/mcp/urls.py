"""Which addresses an agent may open. By default only the web: ``http``,
``https``, ``about:blank`` and ``data:``. ``file:`` would hand local files to
whatever the page (or a prompt injection in it) asks the agent to read;
``chrome:``, ``devtools:``, ``chrome-extension:``, ``view-source:`` reach the
browser itself; ``javascript:`` is an ``eval`` in disguise.

``data:`` stays allowed: its document has an opaque origin, reads no local file
and no other site's data, and gets no browser privilege. Chrome already refuses
a web page's redirect or link to ``file:``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from tellurium.mcp.results import ToolError

WEB_SCHEMES = frozenset({"http", "https", "data"})
OPTION = "--allow-local-urls"


def check(url: str, *, allow_local: bool = False) -> str:
    """*url* if the agent may open it, else a :class:`ToolError` naming why."""
    if allow_local:
        return url
    # Chrome trims what urlsplit keeps (spaces, control characters): judge the same text.
    cleaned = url.strip().strip("\x00\t\n\r\x0b\x0c")
    scheme = urlsplit(cleaned).scheme.lower()
    if scheme in WEB_SCHEMES:
        return url
    if scheme == "about" and cleaned.lower().split("#")[0].split("?")[0] == "about:blank":
        return url
    if not scheme:
        raise ToolError(f"Not a full address: {url!r}. Give one like https://example.com/.")
    raise ToolError(
        f"{scheme}: URLs are refused (local files and browser pages stay out of reach); "
        f"only http, https, about:blank and data: are allowed. The server's user can "
        f"start it with {OPTION}."
    )
