"""StealthProfile: seed-deterministic browser fingerprint."""

from __future__ import annotations

import os
import platform
import random
from dataclasses import dataclass

from tellurium.stealth.data.gpu import GPU_PROFILES
from tellurium.stealth.data.screens import SCREEN_RESOLUTIONS

# ---------------------------------------------------------------------------
# LCG — identical to C++ FingerprintRNG for seed coherence
# ---------------------------------------------------------------------------


class _LCG:
    """LCG identical to C++ FingerprintRNG for seed coherence."""

    def __init__(self, seed: int):
        self._state = seed & 0xFFFFFFFF

    def next_uint32(self) -> int:
        self._state = (self._state * 1664525 + 1013904223) & 0xFFFFFFFF
        return self._state

    def next_double(self) -> float:
        return self.next_uint32() / 4294967295.0

    def next_int(self, min_val: int, max_val: int) -> int:
        return min_val + int(self.next_double() * (max_val - min_val + 1))

    def choice(self, items: list):
        return items[self.next_int(0, len(items) - 1)]

    def weighted_choice(self, items: list, weight_key: str = "weight"):
        total = sum(item[weight_key] for item in items)
        r = self.next_double() * total
        cumulative = 0.0
        for item in items:
            cumulative += item[weight_key]
            if r < cumulative:
                return item
        return items[-1]


# ---------------------------------------------------------------------------
# OS detection helpers
# ---------------------------------------------------------------------------

_REAL_OS_MAP = {
    "Windows": "windows",
    "Darwin": "macos",
    "Linux": "linux",
}

_TIMEZONE_BY_OS = {
    "windows": "America/New_York",
    "macos": "America/Los_Angeles",
    "linux": "America/Chicago",
}

_LOCALE_BY_OS = {
    "windows": "en-US",
    "macos": "en-US",
    "linux": "en-US",
}

_LANGUAGES_BY_OS = {
    "windows": ["en-US", "en"],
    "macos": ["en-US", "en"],
    "linux": ["en-US", "en"],
}

# Client-hints architecture / bitness constants per OS
_ARCH_BY_OS = {
    "windows": "x86",
    "macos": "arm",
    "linux": "x86",
}

_BITNESS_BY_OS = {
    "windows": "64",
    "macos": "64",
    "linux": "64",
}

# Taskbar / dock height subtracted from screen height for availHeight
_TASKBAR_HEIGHT = {
    "windows": 40,
    "macos": 25,
    "linux": 30,
}

# DPR defaults per OS
_DPR_BY_OS = {
    "windows": 1.0,
    "macos": 2.0,
    "linux": 1.0,
}


def _detect_real_os() -> str:
    return _REAL_OS_MAP.get(platform.system(), "linux")


def build_accept_language(languages: list) -> str:
    """Build an ``Accept-Language`` header value from a language list.

    ``["it-IT", "it", "en"]`` -> ``"it-IT, it;q=0.9, en;q=0.8"``.  Shared by
    :meth:`StealthProfile._build_profile` and by ``Browser.launch`` when the
    caller overrides ``languages=`` manually, so the two paths cannot drift.
    """
    return ", ".join(
        f"{lang};q={round(1.0 - 0.1 * i, 1)}" if i > 0 else lang for i, lang in enumerate(languages)
    )


# ---------------------------------------------------------------------------
# User-Agent / Client-Hints builders
# ---------------------------------------------------------------------------

_CH_UA_BRAND_TMPL = '"Chromium";v="{major}", "Google Chrome";v="{major}", "Not-A.Brand";v="99"'

_CH_UA_FULL_VER_TMPL = (
    '"Chromium";v="{full}", "Google Chrome";v="{full}", "Not-A.Brand";v="99.0.0.0"'
)


def _build_ua_windows(version: str) -> str:
    version.split(".")[0]
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version} Safari/537.36"
    )


def _build_ua_macos(version: str) -> str:
    return (
        f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version} Safari/537.36"
    )


def _build_ua_linux(version: str) -> str:
    return (
        f"Mozilla/5.0 (X11; Linux x86_64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version} Safari/537.36"
    )


_UA_BUILDERS = {
    "windows": _build_ua_windows,
    "macos": _build_ua_macos,
    "linux": _build_ua_linux,
}

_PLATFORM_STRINGS = {
    "windows": "Win32",
    "macos": "MacIntel",
    "linux": "Linux x86_64",
}

_PLATFORM_VERSIONS = {
    "windows": "Windows NT 10.0",
    "macos": "10_15_7",
    "linux": "",
}

_CH_UA_PLATFORM_MAP = {
    "windows": "Windows",
    "macos": "macOS",
    "linux": "Linux",
}


# ---------------------------------------------------------------------------
# StealthProfile dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StealthProfile:
    # Core identity
    seed: int
    user_agent: str
    browser_version: str
    platform: str
    platform_version: str
    target_os: str

    # Client Hints
    ch_ua: str
    ch_ua_platform: str
    ch_ua_arch: str
    ch_ua_bitness: str
    ch_ua_full_version_list: str
    ch_ua_mobile: bool

    # Screen
    screen_width: int
    screen_height: int
    screen_avail_height: int
    device_pixel_ratio: float

    # Hardware
    hardware_concurrency: int
    device_memory: int

    # WebGL
    webgl_vendor: str
    webgl_renderer: str

    # Locale / timezone
    languages: list
    timezone: str
    locale: str
    accept_language: str

    # GREASE brand — populated post-construction by Browser.launch() after
    # Browser.getVersion is called on the root session (review 2026-04-15 #5).
    # None means the engine should fall back to the historical literal.
    grease_brand: str | None = None
    grease_version: str | None = None

    # WebRTC public IP — populated post-construction by Browser.launch() after
    # resolve_webrtc_ip() runs (review 2026-04-15 #9, aspect #18).
    # None means no IP spoofing via webrtc.js.
    webrtc_public_ip: str | None = None

    # ------------------------------------------------------------------
    # Internal builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_profile(
        seed: int,
        target_os: str,
        browser_version: str,
        timezone: str | None = None,
        locale: str | None = None,
    ) -> StealthProfile:
        rng = _LCG(seed)

        # GPU
        gpu = rng.weighted_choice(GPU_PROFILES[target_os])

        # Screen
        res = rng.choice(SCREEN_RESOLUTIONS[target_os])
        screen_width, screen_height = res
        taskbar = _TASKBAR_HEIGHT[target_os]
        screen_avail_height = screen_height - taskbar

        # Hardware
        hardware_concurrency = rng.choice([4, 8, 12, 16])
        device_memory = rng.choice([4, 8, 16])

        # DPR
        dpr = _DPR_BY_OS[target_os]

        # UA / client hints
        ua = _UA_BUILDERS[target_os](browser_version)
        major = browser_version.split(".")[0]
        ch_ua = _CH_UA_BRAND_TMPL.format(major=major)
        ch_ua_full = _CH_UA_FULL_VER_TMPL.format(full=browser_version)

        # Locale / timezone
        tz = timezone if timezone is not None else _TIMEZONE_BY_OS[target_os]
        loc = locale if locale is not None else _LOCALE_BY_OS[target_os]
        langs = _LANGUAGES_BY_OS[target_os]
        accept_lang = build_accept_language(langs)

        return StealthProfile(
            seed=seed,
            user_agent=ua,
            browser_version=browser_version,
            platform=_PLATFORM_STRINGS[target_os],
            platform_version=_PLATFORM_VERSIONS[target_os],
            target_os=target_os,
            ch_ua=ch_ua,
            ch_ua_platform=_CH_UA_PLATFORM_MAP[target_os],
            ch_ua_arch=_ARCH_BY_OS[target_os],
            ch_ua_bitness=_BITNESS_BY_OS[target_os],
            ch_ua_full_version_list=ch_ua_full,
            ch_ua_mobile=False,
            screen_width=screen_width,
            screen_height=screen_height,
            screen_avail_height=screen_avail_height,
            device_pixel_ratio=dpr,
            hardware_concurrency=hardware_concurrency,
            device_memory=device_memory,
            webgl_vendor=gpu["vendor"],
            webgl_renderer=gpu["renderer"],
            languages=langs,
            timezone=tz,
            locale=loc,
            accept_language=accept_lang,
        )

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_seed(
        cls,
        seed: int,
        os: str | None = None,
        browser_version: str = "146.0.7680.188",
    ) -> StealthProfile:
        """Create a deterministic profile from a seed."""
        target_os = os if os is not None else _detect_real_os()
        return cls._build_profile(seed, target_os, browser_version)

    @classmethod
    def auto(
        cls,
        browser_version: str = "146.0.7680.188",
    ) -> StealthProfile:
        """Create a profile with a random seed using the real OS."""
        seed = random.randint(1, 0xFFFFFFFF)
        target_os = _detect_real_os()
        return cls._build_profile(seed, target_os, browser_version)

    @classmethod
    def from_proxy(
        cls,
        proxy_ip: str,
        browser_version: str = "146.0.7680.188",
    ) -> StealthProfile:
        """Create a profile with timezone/locale from GeoIP of proxy_ip."""
        timezone: str | None = None
        locale: str | None = None

        try:
            import maxminddb  # type: ignore

            db_path = os.path.join(os.path.dirname(__file__), "data", "GeoLite2-City.mmdb")
            if os.path.exists(db_path):
                with maxminddb.open_database(db_path) as reader:
                    record = reader.get(proxy_ip)
                    if record:
                        tz_val = record.get("location", {}).get("time_zone")
                        if tz_val:
                            timezone = tz_val
                        lang_val = record.get("country", {}).get("names", {}).get("en")
                        if lang_val:
                            locale = "en-US"
        except Exception:  # noqa: BLE001 - locale detection is best-effort
            pass

        seed = random.randint(1, 0xFFFFFFFF)
        target_os = _detect_real_os()
        return cls._build_profile(
            seed, target_os, browser_version, timezone=timezone, locale=locale
        )
