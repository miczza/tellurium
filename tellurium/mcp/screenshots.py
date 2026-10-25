"""Screenshots small enough for an MCP client: at most :data:`SHOT_BYTES` of
base64 per image (clients and models refuse bigger ones). A PNG over the cap
is captured again as JPEG, at lower quality and then smaller scale, and the
result says so."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from tellurium.mcp.results import ToolError

# The image as the client receives it, base64 included.
SHOT_BYTES = 5 * 1024 * 1024
_SCALES = (1.0, 0.5, 0.25, 0.125)
_QUALITIES = (80, 50)

# (format, quality or None, scale) -> the image bytes.
Capture = Callable[[str, int | None, float], Awaitable[bytes]]


@dataclass(frozen=True)
class Shot:
    data: bytes
    mime: str
    format: str
    scale: float
    note: str = ""


def encoded_size(n: int) -> int:
    """The length of *n* bytes in base64."""
    return 4 * ((n + 2) // 3)


async def fit(capture: Capture, *, limit: int = SHOT_BYTES, png: bytes | None = None) -> Shot:
    """The PNG from *capture* (or *png*, already taken) if it fits in *limit*,
    else the first JPEG that does; a :class:`ToolError` if none does."""
    if png is None:
        png = await capture("png", None, 1.0)
    if encoded_size(len(png)) <= limit:
        return Shot(png, "image/png", "png", 1.0)
    for scale in _SCALES:
        for quality in _QUALITIES:
            data = await capture("jpeg", quality, scale)
            if encoded_size(len(data)) <= limit:
                at = f" at {scale:.0%} scale" if scale < 1 else ""
                note = (
                    f"PNG was {_mb(encoded_size(len(png)))}, over the {_mb(limit)} cap: "
                    f"sent as JPEG quality {quality}{at}"
                )
                return Shot(data, "image/jpeg", "jpeg", scale, note)
    raise ToolError(
        f"Screenshot over {_mb(limit)} even as a small JPEG: take a part of the page with ref="
    )


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.1f} MB"
