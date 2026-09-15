"""Stealth engine — orchestrates anti-detection measures."""
from __future__ import annotations
import asyncio
import logging
from tellurium.browser.engine import BrowserEngine
from tellurium.stealth.profile import StealthProfile
from tellurium.stealth.extension import load_script, create_stealth_extension

logger = logging.getLogger("tellurium")

# Auto-attach is restricted to target types we actually stealth-patch.
# 'page' would cause double injection; 'browser' would deadlock because
# the callback awaits Runtime.runIfWaitingForDebugger and browser-level
# targets never wait. Design doc 04 §P1.2.
_STEALTH_TARGET_FILTER: list[dict] = [
    {"type": "iframe", "exclude": False},
    {"type": "worker", "exclude": False},
    {"type": "service_worker", "exclude": False},
    {"type": "shared_worker", "exclude": False},
]


class StealthEngine:
    def __init__(self, engine: BrowserEngine, profile: StealthProfile,
                 headless: bool, has_proxy: bool):
        self._caps = engine.capabilities()
        self._profile = profile
        self._headless = headless
        self._has_proxy = has_proxy
        self._extension_dir: str | None = None
        # Auto-attach is armed on the root session *and* on every page
        # session; guard against patching the same target twice should both
        # ever deliver the same sessionId.
        self._patched_sessions: set[str] = set()

    def build_extension(self) -> str | None:
        """Build the stealth Chrome extension. Returns path or None if not needed."""
        if "native_fingerprint" in self._caps:
            return None  # patched mode — no extension needed

        scripts = self._build_scripts()
        if not scripts:
            return None

        self._extension_dir = create_stealth_extension(scripts)
        return self._extension_dir

    async def apply_to_session(self, session, is_oopif: bool = False) -> None:
        """Apply stealth fixes to a CDP session (tab or OOPIF)."""
        # CDP Emulation fixes (only if backend doesn't handle natively)
        if "native_navigator" not in self._caps:
            await self._set_ua_override(session)

        # Note: client hints are already covered by _set_ua_override()
        # (userAgentMetadata), so "native_client_hints" needs no branch here.

        # Timezone and locale (always, even for patched — CDP is the authority here)
        await session.send("Emulation.setTimezoneOverride", {
            "timezoneId": self._profile.timezone,
        })
        await session.send("Emulation.setLocaleOverride", {
            "locale": self._profile.locale,
        })

        if "native_navigator" not in self._caps:
            await session.send("Emulation.setHardwareConcurrencyOverride", {
                "hardwareConcurrency": self._profile.hardware_concurrency,
            })

        # Headless fixes (always, both backends)
        if self._headless:
            await self._apply_headless_fixes(session, is_oopif=is_oopif)

    async def setup_auto_attach(self, session) -> None:
        """Configure auto-attach for OOPIF and Worker stealth patching.

        T7.7 (design doc 04 §P1.1/§P1.2): ``waitForDebuggerOnStart=True``
        so that a cross-origin iframe / worker target is *frozen* before it
        runs a single line of JS. ``_patch_and_resume`` injects the stealth
        overrides and only then sends ``Runtime.runIfWaitingForDebugger``,
        so an anti-bot running inside the OOPIF or worker never observes an
        unpatched value.

        Must be called on **every page session**, not just the browser-root
        one: empirically (Chrome 153) a browser-level ``Target.setAutoAttach``
        never fires ``Target.attachedToTarget`` for a page's OOPIFs or for a
        page's dedicated workers — only page-session auto-attach does. The
        root session is still wired so browser-scoped service workers are
        covered.

        The ``filter`` restricts auto-attach to target types that we
        actually patch (iframe, worker, service_worker, shared_worker).
        Without the filter Chromium fires auto-attach for every target
        type including 'page' (double injection) and 'browser'
        (deadlock on Runtime.runIfWaitingForDebugger). Design doc 04 §P1.2.
        """
        await session.send("Target.setAutoAttach", {
            "autoAttach": True,
            "waitForDebuggerOnStart": True,
            "flatten": True,
            "filter": _STEALTH_TARGET_FILTER,
        })

    async def wire_session(self, session) -> None:
        """Register the auto-attach listener on *session* and enable it.

        Convenience used by ``Browser.launch`` (root + initial tab) and
        ``Browser.new_tab``. Registering the handler *before* sending
        ``Target.setAutoAttach`` avoids missing a target that attaches
        while the command is in flight.
        """
        session.on("Target.attachedToTarget", self._on_target_attached)
        await self.setup_auto_attach(session)

    def _on_target_attached(self, params: dict) -> None:
        target_info = params.get("targetInfo", {})
        session_id = params.get("sessionId")
        target_type = target_info.get("type", "")
        target_url = target_info.get("url", "") or ""

        # Ensure the router knows about this auto-attached session
        self._ensure_session(session_id)

        if session_id in self._patched_sessions:
            return
        self._patched_sessions.add(session_id)

        loop = asyncio.get_running_loop()
        if "native_fingerprint" in self._caps:
            # Patched: resume immediately
            loop.create_task(self._resume_target(session_id))
        else:
            # Stock: patch then resume
            loop.create_task(
                self._patch_and_resume(session_id, target_type, target_url)
            )

    async def _patch_and_resume(
        self, session_id: str, target_type: str, target_url: str = "",
    ) -> None:
        """Inject stealth into a frozen OOPIF/Worker target, then resume.

        The target is paused (``waitForDebuggerOnStart``), so the resume
        lives in a ``finally``: a failed injection must never leave an
        iframe or worker frozen forever.
        """
        session = self._get_session(session_id)
        try:
            if target_type == "iframe":
                # T7.7: Page.enable is mandatory on a fresh OOPIF session.
                # Without it Chrome accepts
                # Page.addScriptToEvaluateOnNewDocument but does not run the
                # script at document-start — verified empirically: the OOPIF's
                # own inline <script> still observed navigator.webdriver ===
                # true, and our source only landed afterwards (runImmediately).
                await session.send("Page.enable", {})
                await self.apply_to_session(session, is_oopif=True)
                # T7: also push runtime JS overrides into the OOPIF.
                await self.apply_page_scripts(session)
            elif target_type in ("worker", "service_worker", "shared_worker"):
                await self.apply_worker_scripts(session, target_url)
        except Exception:
            logger.debug("Failed to patch target %s", session_id, exc_info=True)
        finally:
            try:
                await session.send(
                    "Runtime.runIfWaitingForDebugger", {}, timeout=10.0,
                )
            except Exception:
                logger.debug("Failed to resume target %s", session_id, exc_info=True)

    async def _resume_target(self, session_id: str) -> None:
        try:
            await self._get_session(session_id).send("Runtime.runIfWaitingForDebugger", {})
        except Exception:
            pass

    def update_profile(self, profile: StealthProfile) -> None:
        """Replace the profile (frozen dataclass) with an updated version.

        Called by Browser.launch() after Browser.getVersion resolves so the
        GREASE brand from the real binary is applied before apply_to_session()
        runs. Must be called before the first CDP override emission.
        """
        self._profile = profile

    def set_router(self, router) -> None:
        """Set the SessionRouter reference for auto-attach handling."""
        self._router = router

    def _ensure_session(self, session_id: str) -> None:
        """Register an auto-attached session in the router if not already known."""
        from tellurium.cdp.transport._session import Session
        if session_id and session_id not in self._router._sessions:
            session = Session(self._router, session_id=session_id)
            self._router._sessions[session_id] = session

    def _get_session(self, session_id: str):
        return self._router.get_session(session_id)

    def _build_scripts(self) -> list[str]:
        """Build the list of JS scripts for the extension.

        T7.5 (2026-04-24): on stock backend, only 4 core scripts are
        emitted (webdriver, chrome_runtime, plugins, keyboard_layout).
        The previous webgl.js / tostring_mask.js / navigator_proto.js
        overrides were removed because they are detection vectors for
        CreepJS regardless of value (see specs/2026-04-24-T7.5-...md).
        webdriver.js stays: tellurium uses `--remote-debugging-pipe`
        which makes navigator.webdriver=true natively (unlike
        --remote-debugging-port which nodriver uses); the spec
        assumption that CDP-only Chrome was naturally false was
        empirically wrong (Task 4 smoke surfaced this). hardwareConcurrency
        / platform are covered by CDP Emulation overrides; WebGL /
        device_memory passthrough on stock; both still rotated on
        patched backend via the C++ FingerprintRNG.
        """
        if "native_fingerprint" in self._caps:
            return []

        p = self._profile
        # T7.6 F4: webdriver.js MUST stay first — it captures the native
        # Function.prototype.toString reference before chrome_runtime.js (and
        # any subsequent script) defines its stub markers. Reordering will
        # break the toString mask cross-realm path. See
        # tests/stealth/test_webdriver_robustness.py for invariants.
        scripts = [
            load_script("webdriver.js"),
            load_script("chrome_runtime.js"),
            load_script("plugins.js"),
            load_script("keyboard_layout.js", {
                "LOCALE": p.locale,
            }),
        ]

        if self._has_proxy or p.webrtc_public_ip:
            scripts.append(load_script("webrtc.js", {
                "WEBRTC_PUBLIC_IP": p.webrtc_public_ip or "null",
            }))

        if self._headless:
            scripts.extend([
                load_script("headless_dimensions.js", {
                    "OUTER_WIDTH": str(p.screen_width),
                    "OUTER_HEIGHT": str(p.screen_avail_height),
                }),
                load_script("headless_permissions.js"),
                load_script("headless_connection.js"),
                load_script("headless_voices.js", {"OS": p.target_os}),
                load_script("headless_media.js"),
            ])

        return scripts

    async def apply_page_scripts(self, session) -> None:
        """Push each stealth JS script via Page.addScriptToEvaluateOnNewDocument.

        Used when --load-extension is unavailable (Chrome branded >=137)
        or when an environment prefers CDP delivery over extension-based.
        Idempotent per session: browser dedups identical sources.
        """
        if "native_navigator" in self._caps:
            # Patched engine already handles these natively; skip JS injection.
            return

        scripts = self._build_scripts()
        for source in scripts:
            await session.send("Page.addScriptToEvaluateOnNewDocument", {
                "source": source,
                "runImmediately": True,   # apply even if a document already exists
            })

    def _build_worker_scripts(self) -> list[str]:
        """JS overrides for worker scope (design doc 04 §P1.2).

        Only the window/worker *mismatch* vectors are patched. In
        particular ``navigator.webdriver`` is intentionally NOT defined:
        empirically (Chrome 153) ``WorkerNavigator`` has no ``webdriver``
        property at all, so defining one would be a new fingerprint, not a
        fix. See ``worker_navigator.js`` for the full rationale and the
        T7.6 design doc "Out of Scope" note on candidate F6.
        """
        if "native_navigator" in self._caps:
            return []
        return [
            load_script("worker_navigator.js", {
                "HARDWARE_CONCURRENCY": self._profile.hardware_concurrency,
            }),
        ]

    async def apply_worker_scripts(self, session, target_url: str = "") -> None:
        """Inject worker-scope overrides via ``Runtime.evaluate``.

        Workers have no ``Page`` domain, so
        ``Page.addScriptToEvaluateOnNewDocument`` is unavailable; the target
        is frozen by ``waitForDebuggerOnStart`` instead, which makes a plain
        ``Runtime.evaluate`` land before the worker script runs.

        ``Runtime.enable`` is never called (architectural guard in
        ``tellurium/cdp/transport/_session.py``).
        """
        if target_url.startswith(("chrome-extension://", "chrome://", "devtools://")):
            # Browser-internal / extension workers: not page-visible, leave
            # them untouched (still resumed by the caller's finally).
            return
        for source in self._build_worker_scripts():
            await session.send("Runtime.evaluate", {
                "expression": source,
                "returnByValue": True,
            }, timeout=10.0)

    async def _set_ua_override(self, session) -> None:
        """Set User-Agent and Client Hints via CDP."""
        p = self._profile
        major = p.browser_version.split(".")[0]

        grease_brand = p.grease_brand or "Not_A Brand"
        grease_version = p.grease_version or "24"
        grease_version_full = (
            p.grease_version + ".0.0.0" if p.grease_version else "24.0.0.0"
        )

        await session.send("Emulation.setUserAgentOverride", {
            "userAgent": p.user_agent,
            "acceptLanguage": p.accept_language,
            "platform": p.platform,
            "userAgentMetadata": {
                "brands": [
                    {"brand": "Chromium", "version": major},
                    {"brand": "Google Chrome", "version": major},
                    {"brand": grease_brand, "version": grease_version},
                ],
                "fullVersionList": [
                    {"brand": "Chromium", "version": p.browser_version},
                    {"brand": "Google Chrome", "version": p.browser_version},
                    {"brand": grease_brand, "version": grease_version_full},
                ],
                "platform": p.ch_ua_platform,
                "platformVersion": p.platform_version,
                "architecture": p.ch_ua_arch,
                "bitness": p.ch_ua_bitness,
                "mobile": p.ch_ua_mobile,
                "model": "",
                "wow64": False,
            },
        })

    async def _apply_headless_fixes(self, session, is_oopif: bool = False) -> None:
        """Apply headless-specific CDP fixes.

        T7.7: ``Emulation.setDeviceMetricsOverride`` is rejected by Chrome on
        subframe targets ("Command can only be executed on top-level
        targets"). Sending it to an OOPIF raised a CDPError that aborted
        ``apply_to_session`` *before* ``apply_page_scripts`` ever ran, which
        is why OOPIFs kept reporting ``navigator.webdriver === true``. The
        override is inherited from the top-level frame anyway.
        """
        p = self._profile
        await session.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
        if not is_oopif:
            await session.send("Emulation.setDeviceMetricsOverride", {
                "width": p.screen_width,
                "height": p.screen_avail_height,
                "deviceScaleFactor": p.device_pixel_ratio,
                "mobile": False,
                "screenWidth": p.screen_width,
                "screenHeight": p.screen_height,
            })
        await session.send("Emulation.setEmulatedMedia", {
            "features": [
                {"name": "prefers-color-scheme", "value": "light"},
                {"name": "prefers-reduced-motion", "value": "no-preference"},
            ],
        })
