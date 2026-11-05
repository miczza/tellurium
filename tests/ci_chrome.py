"""Check, in CI, that the tests run the Chrome the workflow says they run.

``python -m tests.ci_chrome`` with ``STOCK_CHROME`` (setup-chrome's path) in
the environment: ``find_chrome()`` must pick that Chrome, it must launch, and
its major version must be the current stable one (Google's version history,
Linux channel), the same on every system. Exits 1 on any mismatch. It never
runs ``chrome --version``: on Windows that opens a window and never exits.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import urllib.request

_STABLE = (
    "https://versionhistory.googleapis.com/v1/chrome/platforms/linux/channels/stable/versions"
)


def stable_major() -> int:
    with urllib.request.urlopen(_STABLE, timeout=30) as response:
        return int(json.load(response)["versions"][0]["version"].split(".")[0])


def ua_major(user_agent: str) -> int:
    match = re.search(r"Chrome/(\d+)\.", user_agent)
    if not match:
        raise ValueError(f"no Chrome version in {user_agent!r}")
    return int(match.group(1))


async def _launched_user_agent() -> str:
    from tellurium import Browser

    browser = await Browser.launch(headless=True)
    try:
        return str(await browser.main_tab.eval("navigator.userAgent"))
    finally:
        await browser.close()


def main() -> int:
    from tellurium.browser.launcher import find_chrome

    found = asyncio.run(find_chrome())
    stock = os.environ["STOCK_CHROME"]
    print("setup-chrome:", stock)
    print("find_chrome: ", found)
    errors = []
    if os.path.realpath(found) != os.path.realpath(stock):
        errors.append("find_chrome() picks another Chrome than setup-chrome's")
    user_agent = asyncio.run(asyncio.wait_for(_launched_user_agent(), 120))
    print("launched:    ", user_agent)
    major, stable = ua_major(user_agent), stable_major()
    print("stable:      ", stable)
    if major != stable:
        errors.append(f"Chrome {major} is not the current stable {stable}")
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
