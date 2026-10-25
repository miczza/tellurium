"""The byte cap on MCP screenshots, without Chrome: a fake capture whose size
depends on format, quality and scale."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")

from tellurium.mcp import screenshots  # noqa: E402
from tellurium.mcp.results import Reply, ToolError, success  # noqa: E402


class _Capture:
    """PNG of *png* bytes; JPEG is *jpeg_ratio* of it at quality 80, smaller
    at lower quality, and shrinks with the square of the scale."""

    def __init__(self, png: int, jpeg_ratio: float = 0.5):
        self.png, self.jpeg_ratio = png, jpeg_ratio
        self.calls: list[tuple[str, int | None, float]] = []

    async def __call__(self, fmt: str, quality: int | None, scale: float) -> bytes:
        self.calls.append((fmt, quality, scale))
        if fmt == "png":
            size = self.png
        else:
            size = self.png * self.jpeg_ratio * (quality / 80)
        return b"x" * int(size * scale * scale)


def test_encoded_size_is_the_base64_length():
    assert [screenshots.encoded_size(n) for n in (0, 1, 2, 3, 4)] == [0, 4, 4, 4, 8]


async def test_a_png_under_the_cap_is_kept():
    capture = _Capture(png=1000)
    shot = await screenshots.fit(capture, limit=2000)
    assert (shot.mime, shot.format, shot.scale, shot.note) == ("image/png", "png", 1.0, "")
    assert capture.calls == [("png", None, 1.0)]


async def test_a_given_png_is_not_captured_again():
    capture = _Capture(png=10_000)
    shot = await screenshots.fit(capture, limit=2000, png=b"x" * 100)
    assert shot.format == "png" and capture.calls == []


async def test_an_oversized_png_becomes_a_jpeg_with_a_note():
    capture = _Capture(png=3000, jpeg_ratio=0.5)
    shot = await screenshots.fit(capture, limit=3000)
    assert shot.mime == "image/jpeg" and shot.format == "jpeg" and shot.scale == 1.0
    assert screenshots.encoded_size(len(shot.data)) <= 3000
    assert "over the" in shot.note and "JPEG" in shot.note and "scale" not in shot.note


async def test_a_jpeg_still_too_big_is_scaled_down():
    capture = _Capture(png=40_000, jpeg_ratio=0.9)
    shot = await screenshots.fit(capture, limit=4000)
    assert shot.format == "jpeg" and shot.scale < 1.0
    assert screenshots.encoded_size(len(shot.data)) <= 4000
    assert f"{shot.scale:.0%} scale" in shot.note


async def test_nothing_small_enough_is_an_error():
    capture = _Capture(png=10**9, jpeg_ratio=1.0)
    with pytest.raises(ToolError, match="ref="):
        await screenshots.fit(capture, limit=10)
    assert len(capture.calls) <= 12  # bounded work


def test_default_cap_is_5_mb_of_payload():
    assert screenshots.SHOT_BYTES == 5 * 1024 * 1024


def test_reply_carries_the_image_type():
    result = success(Reply("shot", {"ok": True}, image=b"\xff\xd8", image_type="image/jpeg"))
    assert result.content[1].mime_type == "image/jpeg"


async def test_the_jpeg_retries_share_one_time_budget():
    import asyncio
    import time

    class _Slow(_Capture):
        async def __call__(self, fmt, quality, scale):
            if fmt == "jpeg":
                await asyncio.sleep(0.15)
            return await super().__call__(fmt, quality, scale)

    # Small fake images: a 1 GB one costs a quarter second to build, outside any budget.
    capture = _Slow(png=10**4, jpeg_ratio=1.0)
    started = time.monotonic()
    with pytest.raises(ToolError, match="in time"):
        await screenshots.fit(capture, limit=10, shrink_budget=0.4, min_attempt=0.05)
    assert time.monotonic() - started < 0.6
    assert len(capture.calls) <= 4


async def test_an_attempt_is_cut_at_the_end_of_the_budget():
    import asyncio
    import time

    class _Hung(_Capture):
        async def __call__(self, fmt, quality, scale):
            if fmt == "jpeg":
                await asyncio.sleep(30)
            return await super().__call__(fmt, quality, scale)

    started = time.monotonic()
    with pytest.raises(ToolError, match="in time"):
        await screenshots.fit(_Hung(png=10**4), limit=10, shrink_budget=0.3, min_attempt=0.05)
    assert time.monotonic() - started < 0.5


async def test_no_attempt_starts_without_its_minimum_time_left():
    import asyncio

    class _Slow(_Capture):
        async def __call__(self, fmt, quality, scale):
            if fmt == "jpeg":
                await asyncio.sleep(0.15)
            return await super().__call__(fmt, quality, scale)

    capture = _Slow(png=10**4, jpeg_ratio=1.0)
    with pytest.raises(ToolError, match="in time"):
        await screenshots.fit(capture, limit=10, shrink_budget=0.3, min_attempt=0.2)
    assert [c[0] for c in capture.calls] == ["png", "jpeg"]  # 0.15 s left < 0.2: stop


async def test_page_metrics_have_their_own_timeout(monkeypatch):
    import asyncio

    from tellurium.mcp import pages

    class _HungTab:
        async def send_cdp(self, method, params=None):
            await asyncio.sleep(60)

    import time

    monkeypatch.setattr(pages, "METRICS_TIMEOUT", 0.05)
    capture = pages._viewport_capture(_HungTab())
    for call in (pages._full_page(_HungTab()), capture("jpeg", 80, 0.5)):
        started = time.monotonic()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(call, 2)
        assert time.monotonic() - started < 1  # its own timeout, not the outer one
