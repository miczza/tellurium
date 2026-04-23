#!/usr/bin/env python3
"""Test canvas fingerprint variation for geometry-only operations (no text).

Verifies that the Skia AA perturbation (C4.6) produces different canvas
hashes across seeds even when no fillText/strokeText is used.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tellurium import Browser


CHROMIUM_TELLURIDE_PATH = "/home/miczza/PycharmProjects/chromium-telluride/src/out/Release/chrome"

GEOMETRY_ONLY_JS = """
(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 200;
    canvas.height = 200;
    const ctx = canvas.getContext('2d');

    // Arc
    ctx.beginPath();
    ctx.arc(50, 50, 30, 0, Math.PI * 2);
    ctx.fillStyle = '#ff6600';
    ctx.fill();

    // Bezier curve
    ctx.beginPath();
    ctx.moveTo(10, 100);
    ctx.bezierCurveTo(30, 50, 120, 150, 150, 100);
    ctx.strokeStyle = '#3366cc';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Gradient rectangle
    const grad = ctx.createLinearGradient(0, 0, 200, 0);
    grad.addColorStop(0, '#ff0000');
    grad.addColorStop(1, '#0000ff');
    ctx.fillStyle = grad;
    ctx.fillRect(10, 140, 180, 50);

    // Diagonal line
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(200, 200);
    ctx.strokeStyle = '#009900';
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // Quadratic curve
    ctx.beginPath();
    ctx.moveTo(150, 20);
    ctx.quadraticCurveTo(180, 80, 120, 120);
    ctx.strokeStyle = '#990099';
    ctx.stroke();

    return canvas.toDataURL();
})()
"""


async def get_canvas_hash(chrome_path: str, seed: int) -> str:
    browser = await Browser.launch(
        headless=False,
        executable=chrome_path,
        args=[
            f"--fingerprint={seed}",
            "--fingerprint-platform=linux",
            "--no-sandbox",
        ],  # Note: --disable-accelerated-2d-canvas auto-added by Blink when --fingerprint is set
    )
    try:
        tab = await browser.new_tab()
        await tab.get("about:blank")
        result = await tab.eval(GEOMETRY_ONLY_JS)
        return result
    finally:
        await browser.close()


async def main():
    chrome = sys.argv[1] if len(sys.argv) > 1 else CHROMIUM_TELLURIDE_PATH
    seeds = [42069, 12345, 99999, 1, 2]
    hashes = {}

    for seed in seeds:
        h = await get_canvas_hash(chrome, seed)
        h = str(h) if h is not None else ""
        hashes[seed] = h
        print(f"seed={seed}: {h[:60]}...")

    unique = len(set(hashes.values()))
    print(f"\n{unique}/{len(seeds)} unique hashes from {len(seeds)} seeds")

    if unique == len(seeds):
        print("PASS: all seeds produce unique geometry-only canvas hashes")
    elif unique == 1:
        print("FAIL: all seeds produce identical geometry-only canvas hash")
        print("The AA perturbation is not affecting geometric shapes")
        sys.exit(1)
    else:
        print(f"PARTIAL: {unique} unique out of {len(seeds)} seeds")
        print("Some seeds may collide (coverage_bias has only 3 values)")
        print("Check if snap_offset is producing variation")


if __name__ == "__main__":
    asyncio.run(main())
