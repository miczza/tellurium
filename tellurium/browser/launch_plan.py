"""Launch plan — everything Chrome is started with, composed before it starts.

:class:`LaunchPlan` picks the engine and its executable, checks the extensions,
starts the proxy forwarder and makes the temporary profile (both owned by the
:class:`~tellurium.browser.process.BrowserProcess` it is given), looks up the
proxy's time zone and languages, builds the stealth profile and engine, and
assembles the command line. :meth:`Browser.launch` and :class:`RawChrome` start
Chrome from it.
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import logging
import os
import threading
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, TypeVar

from tellurium.browser.engine import BrowserEngine, StockEngine, select_engine
from tellurium.browser.launcher import (
    _detect_chrome_version,
    build_chrome_flags,
    build_load_extension_flag,
    check_chrome_version_for_extensions,
    validate_extension_paths,
)
from tellurium.browser.process import BrowserProcess
from tellurium.browser.proxy import forwarder_for, proxy_server_flag
from tellurium.stealth._grease import parse_grease_brands, parse_product_version
from tellurium.stealth._webrtc import resolve_webrtc_ip
from tellurium.stealth.engine import refuse_user_agent_arg

logger = logging.getLogger("tellurium")

#: Keeps WebRTC's UDP inside the proxy: no direct candidate leaks the real IP.
PROXIED_WEBRTC_FLAG = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"

#: Seconds the whole GeoIP step (exit IP and country) may take; then Chrome's defaults.
GEOIP_TIMEOUT = 10.0
#: Seconds ``webrtc_ip='auto'`` may take to resolve the proxy's host name.
DNS_TIMEOUT = 10.0

_T = TypeVar("_T")


@dataclasses.dataclass(kw_only=True)
class LaunchPlan:
    """The options of a launch (see :meth:`Browser.launch`) and what they compose to.

    *geoip* takes the time zone and languages from the proxy's exit IP and
    *proxied_webrtc_only* adds :data:`PROXIED_WEBRTC_FLAG` with a proxy; *stealth*
    implies both. Manual *timezone* and *languages* win over the exit IP.
    :meth:`compose` fills the fields after the options.
    """

    headless: bool = False
    executable: str | None = None
    browser: str = "stock"
    user_data_dir: str | None = None
    args: list[str] | None = None
    proxy: str | None = None
    stealth: bool = False
    seed: int | None = None
    extensions: list[str] | None = None
    chromium_version: str | None = None
    chromium_sha256: str | None = None
    auto_security_update: bool = False
    webrtc_ip: str | None = None
    timezone: str | None = None
    languages: list[str] | None = None
    viewport: tuple[int, int] | None = None
    geoip: bool = False
    proxied_webrtc_only: bool = False

    engine: BrowserEngine | None = dataclasses.field(init=False, default=None)
    chrome_path: str = dataclasses.field(init=False, default="")
    profile_dir: str = dataclasses.field(init=False, default="")
    flags: list[str] = dataclasses.field(init=False, default_factory=list)
    #: The time zone Chrome is meant to have (manual, exit IP or stealth profile), or None.
    effective_timezone: str | None = dataclasses.field(init=False, default=None)
    #: ``webrtc_ip`` as the native patch understands it (an IP literal), or None.
    resolved_webrtc_ip: str | None = dataclasses.field(init=False, default=None)
    #: Set as soon as it exists: whoever owns the launch closes it on failure.
    stealth_engine: Any = dataclasses.field(init=False, default=None)
    stealth_profile: Any = dataclasses.field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.languages is not None:
            if not isinstance(self.languages, (list, tuple)) or not self.languages:
                raise ValueError("languages must be a non-empty list, e.g. ['it-IT', 'it']")
            self.languages = list(self.languages)
        if self.viewport is not None:
            if len(tuple(self.viewport)) != 2:
                raise ValueError("viewport must be a (width, height) tuple")
            if int(self.viewport[0]) <= 0 or int(self.viewport[1]) <= 0:
                raise ValueError("viewport width and height must be positive")

    @property
    def seed_used(self) -> int | None:
        """The fingerprint seed something applies, or None.

        The patched engine draws one when none is given; with the stock engine
        only the stealth profile uses it.
        """
        engine_seed = getattr(self.engine, "seed", None)
        if engine_seed is not None:
            return engine_seed
        return self.seed if self.stealth else None

    async def compose(self, proc: BrowserProcess) -> None:
        """Resolve everything up to Chrome's command line (:attr:`flags`).

        The forwarder and the temporary profile are recorded on *proc* as soon
        as they exist: on failure or cancellation ``proc.close()`` releases them
        (and the caller closes :attr:`stealth_engine`).
        """
        # Refused before any async work or resource.
        validate_extension_paths(self.extensions or [])
        if self.stealth:
            refuse_user_agent_arg(self.args)
        # The native patch only understands an IP literal (or its own 'disable',
        # which drops every candidate), so 'auto' must reach it already resolved
        # and our 'disable' — no spoofing — must leave the flag out entirely.
        if self.webrtc_ip is not None:
            self.resolved_webrtc_ip = await _webrtc_public_ip(self.webrtc_ip, self.proxy)

        self.engine = select_engine(
            self.browser,
            self.executable,
            chromium_version=self.chromium_version,
            chromium_sha256=self.chromium_sha256,
            auto_security_update=self.auto_security_update,
            webrtc_ip_flag=self.resolved_webrtc_ip,
        )
        if (
            self.resolved_webrtc_ip is not None
            and not self.stealth
            and isinstance(self.engine, StockEngine)
        ):
            logger.warning(
                "webrtc_ip=%r has no effect on stock Chrome without stealth: only the "
                "patched engine (or the stealth script) rewrites the WebRTC candidates",
                self.webrtc_ip,
            )
        # Engines resolve the executable off the event loop.
        self.chrome_path = await self.engine.get_executable()
        if self.extensions:
            await self._check_extensions()

        # Validated before any resource exists (scheme, SOCKS credentials).
        forwarder = forwarder_for(self.proxy) if self.proxy else None
        proxy_flag = proxy_server_flag(self.proxy) if self.proxy else None
        if forwarder is not None:
            await proc.start_forwarder(forwarder)
            proxy_flag = f"http://127.0.0.1:{forwarder.port}"
        self.profile_dir = self.user_data_dir or proc.make_temp_profile()

        geo = None
        if self.proxy and (self.geoip or self.stealth):
            geo = await _exit_geo(self.proxy, proc.forwarder)
        if self.stealth:
            found = await self._build_stealth(geo)
            engine_args = self.engine.build_args(self.stealth_profile)
            self.effective_timezone = self.stealth_profile.timezone
        else:
            found = None
            timezone = self.timezone
            if timezone is None and geo is not None:
                timezone = geo.timezone
            self.effective_timezone = timezone
            seeded = SimpleNamespace(seed=self.seed, timezone=timezone)
            engine_args = self.engine.build_args(seeded)

        self.flags = build_chrome_flags(
            headless=self.headless,
            user_data_dir=self.profile_dir,
            proxy=proxy_flag,
            extra_args=(self.args or []) + self._identity_flags(geo, found),
            engine_args=engine_args,
        )

    async def _check_extensions(self) -> None:
        """Branded Chrome 137+ ignores ``--load-extension``: refuse it, and warn once."""
        version = await asyncio.to_thread(_detect_chrome_version, self.chrome_path)
        p = self.chrome_path.lower()
        is_branded_chrome = (
            "google-chrome" in p  # linux binary name
            or p.endswith("google chrome")  # macOS .app bundle
            or "\\google\\chrome\\" in p  # Windows install path
            or "/google/chrome/" in p  # normalized Windows path
        )
        check_chrome_version_for_extensions(
            executable=self.chrome_path,
            version=version,
            is_branded_chrome=is_branded_chrome,
            extensions=self.extensions,
        )
        if os.environ.get("TELLURIUM_SUPPRESS_EXTENSION_WARNING") != "1":
            logger.warning(
                "User extensions loaded: %s. "
                "Extensions expose 4 fingerprint vectors: "
                "(1) chrome.runtime.sendMessage enumeration, "
                "(2) DOM signatures (injected elements/stylesheets), "
                "(3) Window globals (e.g. window.__extension_*), "
                "(4) web_accessible_resources probing via chrome-extension://<id>/.",
                ", ".join(self.extensions or []),
            )

    async def _build_stealth(self, geo: Any) -> tuple[int, ...] | None:
        """Stealth profile (seed, exit IP, manual overrides, binary version) and engine.

        Returns the version read from the binary, or None when it is unknown.
        """
        from tellurium.stealth.engine import StealthEngine
        from tellurium.stealth.profile import StealthProfile, build_accept_language

        if self.seed is not None:
            profile = StealthProfile.from_seed(self.seed)
        else:
            profile = StealthProfile.auto()
        if geo is not None:
            profile = dataclasses.replace(
                profile,
                languages=geo.languages,
                timezone=geo.timezone,
                locale=geo.languages[0],
                accept_language=", ".join(
                    f"{lang};q={1.0 - i * 0.1:.1f}" if i > 0 else lang
                    for i, lang in enumerate(geo.languages)
                ),
            )
        # Manual overrides win over both GeoIP and the seeded defaults
        # (design doc 01 §"Override manuali (ignorano auto-detect)").
        manual: dict[str, Any] = {}
        if self.timezone is not None:
            manual["timezone"] = self.timezone
        if self.languages is not None:
            manual["languages"] = self.languages
            manual["locale"] = self.languages[0]
            manual["accept_language"] = build_accept_language(self.languages)
        if manual:
            profile = dataclasses.replace(profile, **manual)
        # The UA goes on the command line too: it needs the binary's version
        # now, before Browser.getVersion can tell.
        if found := await asyncio.to_thread(_detect_chrome_version, self.chrome_path):
            profile = profile.with_browser_version(".".join(map(str, found)))

        self.stealth_profile = profile
        self.stealth_engine = StealthEngine(
            self.engine, profile, self.headless, self.proxy is not None
        )
        return found

    def _identity_flags(self, geo: Any, found: tuple[int, ...] | None) -> list[str]:
        """Languages, window size, User-Agent, extensions and WebRTC policy."""
        flags: list[str] = []
        # Languages: let Chrome derive both navigator.languages and the
        # Accept-Language header (with its native q-values) from the
        # --accept-lang pref. Overriding acceptLanguage via
        # Emulation.setUserAgentOverride leaks the raw string into
        # navigator.languages (["en-US", "en;q=0.9"]) and produces a
        # malformed header ("en-US, en;q=0.9;q=0.9"). Measured on Chrome 153.
        languages = self.languages
        if languages is None and self.stealth_profile is not None:
            languages = self.stealth_profile.languages
        elif languages is None and geo is not None:
            languages = geo.languages
        if languages:
            flags.append("--accept-lang=" + ",".join(languages))

        if self.viewport is not None:
            flags.append(f"--window-size={int(self.viewport[0])},{int(self.viewport[1])}")

        user_exts = self.extensions or []
        stealth_ext = None
        if self.stealth_engine is not None:
            # Only with the version read from the binary: flag and override
            # then name the same one.
            ua_flag = self.stealth_engine.user_agent_flag() if found else None
            if ua_flag:
                flags.append(ua_flag)
            stealth_ext = self.stealth_engine.build_extension()
        if stealth_ext or user_exts:
            flags.append(
                build_load_extension_flag(
                    tellurium_stealth_path=stealth_ext, user_extensions=user_exts
                )
            )
        # Note: --disable-blink-features=AutomationControlled is intentionally
        # NOT added. Chrome shows an "unsupported command-line flag" warning
        # bar when it is present, which is itself a detection signal. The
        # stealth extension's webdriver.js overrides navigator.webdriver via JS
        # injection because --remote-debugging-pipe makes the native value true.
        if self.proxy and (self.stealth or self.proxied_webrtc_only):
            flags.append(PROXIED_WEBRTC_FLAG)
        return flags

    async def align_stealth(self, root: Any) -> None:
        """Align the stealth profile with the running binary (after Chrome started).

        Reads the real product version and GREASE brand from ``Browser.getVersion``
        (review 2026-04-15 #5/#9) and adds the resolved WebRTC IP, in a single
        profile update. Without an answer the engine keeps its fallbacks
        ("Not_A Brand"/"24", no WebRTC rewrite).
        """
        if self.stealth_engine is None or self.stealth_profile is None:
            return
        try:
            version_info = await root.send("Browser.getVersion", {}, timeout=5.0)
        except Exception:  # noqa: BLE001 - best-effort version probe
            version_info = {}
        profile = self.stealth_profile
        # Align UA / Client Hints with the version the binary really has
        # ("Chrome/153.0.8010.36", "HeadlessChrome/..."): the profile's
        # default browser_version is only a fallback.
        real_version = parse_product_version(version_info.get("product", ""))
        if real_version and real_version != profile.browser_version:
            profile = profile.with_browser_version(real_version)
        replace_kwargs: dict = {}
        raw_brands = version_info.get("userAgentData", {}).get("brands") or []
        if raw_brands:
            g_brand, g_version = parse_grease_brands(raw_brands)
            replace_kwargs["grease_brand"] = g_brand
            replace_kwargs["grease_version"] = g_version
        if self.resolved_webrtc_ip is not None:
            replace_kwargs["webrtc_public_ip"] = self.resolved_webrtc_ip
        if replace_kwargs:
            profile = dataclasses.replace(profile, **replace_kwargs)
        if profile is not self.stealth_profile:
            self.stealth_engine.update_profile(profile)
            self.stealth_profile = profile


async def _exit_geo(proxy: str, forwarder: Any) -> Any:
    """Time zone and languages of the proxy's exit IP, or None (best effort).

    Every lookup request goes through the proxy (its forwarder, if any); the
    whole step is bounded by :data:`GEOIP_TIMEOUT`.
    """
    from tellurium.stealth.geoip import exit_geo

    port = forwarder.port if forwarder is not None else None
    # Off the loop: the lookup goes through the forwarder on it.
    lookup = functools.partial(exit_geo, proxy, port, timeout=GEOIP_TIMEOUT)
    try:
        return await _on_own_thread(lookup, timeout=GEOIP_TIMEOUT, name="tellurium-geoip")
    except Exception as e:  # noqa: BLE001 - GeoIP is best-effort
        if isinstance(e, asyncio.TimeoutError):
            e = f"no answer within {GEOIP_TIMEOUT:g} s"
        logger.warning("GeoIP not available: %s. Using default locale.", e)
        return None


async def _webrtc_public_ip(setting: str, proxy: str | None) -> str | None:
    """:func:`resolve_webrtc_ip`, with the DNS lookup of 'auto' off the loop and bounded."""
    if setting != "auto":
        return resolve_webrtc_ip(setting, proxy=proxy)
    lookup = functools.partial(resolve_webrtc_ip, setting, proxy=proxy)
    try:
        return await _on_own_thread(lookup, timeout=DNS_TIMEOUT, name="tellurium-dns")
    except asyncio.TimeoutError:
        raise ValueError(
            f"Could not resolve the proxy host for webrtc_ip='auto' within {DNS_TIMEOUT:g} s"
        ) from None


async def _on_own_thread(call: Callable[[], _T], *, timeout: float, name: str) -> _T:
    """Run the blocking *call* on a daemon thread of its own, for at most *timeout* s.

    Not on asyncio's default executor: a call given up on (timed out or
    cancelled) runs on until its own timeouts end it, and a few of those there
    would starve the off-loop steps of ``BrowserProcess.close()``. Cancellation
    and :class:`asyncio.TimeoutError` return at once.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future = loop.create_future()

    def deliver(result: Any, error: BaseException | None) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def run() -> None:
        result, error = None, None
        try:
            result = call()
        except Exception as e:  # noqa: BLE001 - handed to the awaiting task
            error = e
        try:
            loop.call_soon_threadsafe(deliver, result, error)
        except RuntimeError:  # the loop is closed: nobody is waiting any more
            pass

    threading.Thread(target=run, name=name, daemon=True).start()
    return await asyncio.wait_for(future, timeout)
