"""End-to-end tests for the patched backend (chromium-telluride).

Skipped unless a patched binary is available:
  * ``TELLURIUM_PATCHED_EXECUTABLE=/path/to/chrome``, or
  * a release installed in the cache (``tellurium download-browser --browser patched``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tellurium.browser import _cache


def _patched_binary() -> Path | None:
    env = os.environ.get("TELLURIUM_PATCHED_EXECUTABLE")
    if env and Path(env).is_file():
        return Path(env)
    browsers = _cache.installed_browsers()
    if browsers:
        default = next((b for b in browsers if b.is_current), browsers[0])
        return default.binary
    return None


@pytest.fixture(scope="module")
def patched_binary() -> Path:
    binary = _patched_binary()
    if binary is None:
        pytest.skip(
            "no chromium-telluride binary (set TELLURIUM_PATCHED_EXECUTABLE "
            "or run `tellurium download-browser --browser patched`)"
        )
    return binary


def _launch_args(binary: Path) -> list[str]:
    # Release tarballs may ship without the SUID chrome_sandbox helper.
    return [] if (binary.parent / "chrome_sandbox").is_file() else ["--no-sandbox"]


# Same probe as chromium-telluride/scripts/dump-fingerprint.js (canvas T1.1),
# so results are comparable with the fork's golden fingerprints.
CANVAS_DATAURL = r"""
(() => {
  const canvas = document.createElement('canvas'); canvas.width = 200; canvas.height = 50;
  const ctx = canvas.getContext('2d');
  ctx.textBaseline = 'top'; ctx.font = '14px Arial'; ctx.fillStyle = '#f60';
  ctx.fillRect(125, 1, 62, 20); ctx.fillStyle = '#069';
  ctx.fillText('Cwm fjordbank glyphs vext quiz, \u{1F603}', 2, 15);
  ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
  ctx.fillText('Cwm fjordbank glyphs vext quiz, \u{1F603}', 4, 17);
  ctx.beginPath(); ctx.arc(50, 25, 20, 0, Math.PI * 2); ctx.closePath(); ctx.fill();
  return canvas.toDataURL();
})()
"""


async def _canvas_hash(binary: Path, seed: int) -> str:
    import hashlib

    from tellurium import Browser

    browser = await Browser.launch(
        browser="patched",
        executable=str(binary),
        headless=True,
        seed=seed,
        args=_launch_args(binary),
    )
    async with browser:
        tab = await browser.new_tab("about:blank")
        data_url = await tab.eval(CANVAS_DATAURL)
        return hashlib.sha256(data_url.encode()).hexdigest()


async def test_patched_launch_passes_fingerprint_flag(patched_binary):
    from tellurium import Browser

    browser = await Browser.launch(
        browser="patched",
        executable=str(patched_binary),
        headless=True,
        seed=42069,
        args=_launch_args(patched_binary),
    )
    async with browser:
        assert browser._engine.seed == 42069
        cmdline = Path(f"/proc/{browser._process.pid}/cmdline")
        if cmdline.exists():
            # Chromium rewrites its argv area as one space-joined string.
            argv = cmdline.read_bytes().replace(b"\0", b" ").split()
            assert b"--fingerprint=42069" in argv
            assert not any(a.startswith(b"--fingerprint-timezone") for a in argv)
        tab = await browser.new_tab("about:blank")
        assert await tab.eval("navigator.webdriver") is False
        ua = await tab.eval("navigator.userAgent")
        assert "Chrome/" in ua


async def test_patched_random_seed_when_none_given(patched_binary):
    from tellurium import Browser

    browser = await Browser.launch(
        browser="patched",
        executable=str(patched_binary),
        headless=True,
        args=_launch_args(patched_binary),
    )
    async with browser:
        assert browser._engine.seed is not None


async def test_patched_canvas_deterministic_per_seed(patched_binary):
    """Same seed -> same canvas noise; different seed -> different (native patch)."""
    a = await _canvas_hash(patched_binary, 42069)
    b = await _canvas_hash(patched_binary, 42069)
    c = await _canvas_hash(patched_binary, 99999)
    assert a == b
    assert a != c


async def test_patched_stealth_true_skips_js_injection(patched_binary):
    """With native_fingerprint capability the JS stealth scripts are not built."""
    from tellurium import Browser

    browser = await Browser.launch(
        browser="patched",
        executable=str(patched_binary),
        headless=True,
        stealth=True,
        seed=7,
        args=_launch_args(patched_binary),
    )
    async with browser:
        eng = browser._stealth_engine
        assert eng is not None
        assert "native_fingerprint" in browser._engine.capabilities()
        tab = await browser.new_tab("about:blank")
        assert await tab.eval("navigator.webdriver") is False
