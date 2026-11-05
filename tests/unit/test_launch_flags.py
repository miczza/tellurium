"""Browser.launch passes Chrome the same command line as before LaunchPlan existed.

Each case is launched up to the spawn, where the flags are captured; temporary
paths and the forwarder's port are normalized. The expected lists were taken
from ``Browser.launch`` as it was before the extraction (master f8ffe71).
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile

import pytest

from tellurium.browser import engine as engine_mod
from tellurium.browser import launch_plan
from tellurium.browser.browser import Browser
from tellurium.browser.process import BrowserProcess
from tellurium.stealth import geoip
from tellurium.stealth import profile as profile_mod
from tellurium.stealth.geoip import GeoResult

ROME = GeoResult(country="IT", timezone="Europe/Rome", languages=["it-IT", "en"])

CASES: dict[str, dict] = {
    "default": {"headless": True},
    "headed_identity": {
        "viewport": (1280, 800),
        "languages": ["it-IT", "it"],
        "args": ["--mute-audio"],
    },
    "socks_proxy": {"headless": True, "proxy": "socks5://127.0.0.1:1080"},
    "proxy_with_credentials": {"headless": True, "proxy": "http://u:p@127.0.0.1:9"},
    "patched_manual": {
        "headless": True,
        "browser": "patched",
        "seed": 7,
        "timezone": "Europe/Rome",
        "webrtc_ip": "203.0.113.4",
    },
    "stealth_stock": {"headless": True, "stealth": True, "seed": 3},
    "stealth_patched_geoip": {
        "headless": True,
        "stealth": True,
        "browser": "patched",
        "seed": 11,
        "proxy": "http://127.0.0.1:9",
    },
    "stealth_overrides": {
        "stealth": True,
        "seed": 3,
        "languages": ["fr-FR"],
        "timezone": "America/New_York",
        "viewport": (800, 600),
        "user_data_dir": "<user_data_dir>",
    },
}

#: What every launch starts with (the profile flag follows).
COMMON = [
    "--remote-debugging-pipe",
    "--no-first-run",
    "--no-default-browser-check",
    "--no-service-autorun",
    "--disable-breakpad",
    "--disable-dev-shm-usage",
    "--disable-infobars",
]

EXPECTED: dict[str, list[str]] = {
    "default": [
        *COMMON,
        "--user-data-dir=<tmp>",
        "--headless=new",
    ],
    "headed_identity": [
        *COMMON,
        "--user-data-dir=<tmp>",
        "--mute-audio",
        "--accept-lang=it-IT,it",
        "--window-size=1280,800",
    ],
    "patched_manual": [
        *COMMON,
        "--user-data-dir=<tmp>",
        "--headless=new",
        "--fingerprint=7",
        "--fingerprint-timezone=Europe/Rome",
        "--fingerprint-webrtc-ip=203.0.113.4",
    ],
    "proxy_with_credentials": [
        *COMMON,
        "--user-data-dir=<tmp>",
        "--headless=new",
        "--proxy-server=<forwarder>",
    ],
    "socks_proxy": [
        *COMMON,
        "--user-data-dir=<tmp>",
        "--headless=new",
        "--proxy-server=socks5://127.0.0.1:1080",
    ],
    "stealth_overrides": [
        *COMMON,
        "--user-data-dir=<user_data_dir>",
        "--accept-lang=fr-FR",
        "--window-size=800,600",
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.7000.1 Safari/537.36",
        "--load-extension=<tmp>",
    ],
    "stealth_patched_geoip": [
        *COMMON,
        "--user-data-dir=<tmp>",
        "--headless=new",
        "--proxy-server=http://127.0.0.1:9",
        "--accept-lang=it-IT,en",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--fingerprint=11",
        "--fingerprint-platform=linux",
        "--fingerprint-timezone=Europe/Rome",
    ],
    "stealth_stock": [
        *COMMON,
        "--user-data-dir=<tmp>",
        "--headless=new",
        "--accept-lang=en-US,en",
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.7000.1 Safari/537.36",
        "--load-extension=<tmp>",
    ],
}


class _Spawned(Exception):
    pass


async def captured_flags(mp: pytest.MonkeyPatch, kwargs: dict) -> list[str]:
    """The flags ``Browser.launch(**kwargs)`` hands to Chrome, normalized."""

    async def fake_exec(self):
        return "/opt/fake/chrome"

    flags: list[str] = []

    async def capture(self, chrome_path, chrome_flags, *rest, **kw):
        flags.extend(chrome_flags)
        raise _Spawned

    def exit_ip(*_a, **_kw):
        return "203.0.113.5"

    mp.setattr(engine_mod.StockEngine, "get_executable", fake_exec)
    mp.setattr(engine_mod.PatchedEngine, "get_executable", fake_exec)
    mp.setattr(BrowserProcess, "spawn", capture)
    mp.setattr(geoip, "resolve_exit_ip", exit_ip)
    mp.setattr(geoip, "resolve_geoip", lambda *_a, **_kw: ROME)
    mp.setattr(geoip, "exit_geo", lambda *_a, **_kw: ROME, raising=False)
    mp.setattr(launch_plan, "detect_chrome_version", lambda _p: (150, 0, 7000, 1))
    # The stealth profile's User-Agent follows the host system: the expected lists are Linux's.
    mp.setattr(profile_mod, "_detect_real_os", lambda: "linux")
    kwargs = dict(kwargs)
    with tempfile.TemporaryDirectory(prefix="tlrflags") as user_data_dir:
        if kwargs.get("user_data_dir"):
            kwargs["user_data_dir"] = user_data_dir
        with pytest.raises(_Spawned):
            await Browser.launch(**kwargs)
        return _normalized(flags, user_data_dir)


def _normalized(flags: list[str], user_data_dir: str) -> list[str]:
    tmp = re.escape(tempfile.gettempdir())
    out = []
    for flag in flags:
        flag = flag.replace(user_data_dir, "<user_data_dir>")
        flag = re.sub(tmp + r"[\\/]tellurium_[^,=\s]+", "<tmp>", flag)
        flag = re.sub(
            r"--proxy-server=http://127\.0\.0\.1:(?!9$)\d+", "--proxy-server=<forwarder>", flag
        )
        out.append(flag)
    return out


@pytest.mark.parametrize("case", sorted(CASES))
async def test_browser_launch_flags_are_unchanged(case, monkeypatch):
    assert await captured_flags(monkeypatch, CASES[case]) == EXPECTED[case]


if __name__ == "__main__":  # prints the expected lists for the checkout on PYTHONPATH

    async def _dump() -> None:
        out = {}
        for case, kwargs in sorted(CASES.items()):
            with pytest.MonkeyPatch.context() as mp:
                out[case] = await captured_flags(mp, kwargs)
        print(json.dumps(out, indent=1))

    asyncio.run(_dump())
