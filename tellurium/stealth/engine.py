"""Stealth engine — orchestrates anti-detection measures."""
from __future__ import annotations
import asyncio
import logging
from tellurium.browser.engine import BrowserEngine
from tellurium.stealth.profile import StealthProfile
from tellurium.stealth.extension import load_script, create_stealth_extension

logger = logging.getLogger("tellurium")


class StealthEngine:
    def __init__(self, engine: BrowserEngine, profile: StealthProfile,
                 headless: bool, has_proxy: bool):
        self._caps = engine.capabilities()
        self._profile = profile
        self._headless = headless
        self._has_proxy = has_proxy
        self._extension_dir: str | None = None

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

        if "native_client_hints" not in self._caps:
            # Already included in _set_ua_override via userAgentMetadata
            pass

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
            await self._apply_headless_fixes(session)

    async def setup_auto_attach(self, root_session) -> None:
        """Configure auto-attach for OOPIF and Worker stealth patching.

        We use ``waitForDebuggerOnStart=False`` to avoid interfering with
        explicit ``Target.attachToTarget`` calls (e.g. from ``new_tab``).
        The stealth extension's content-scripts (``document_start``, ``all_frames``)
        handle JS-level patches; CDP emulation settings propagate automatically.
        """
        await root_session.send("Target.setAutoAttach", {
            "autoAttach": True,
            "waitForDebuggerOnStart": False,
            "flatten": True,
        })

    def _on_target_attached(self, params: dict) -> None:
        target_info = params.get("targetInfo", {})
        session_id = params.get("sessionId")
        target_type = target_info.get("type", "")

        # Ensure the router knows about this auto-attached session
        self._ensure_session(session_id)

        if "native_fingerprint" in self._caps:
            # Patched: resume immediately
            asyncio.get_event_loop().create_task(
                self._resume_target(session_id)
            )
        else:
            # Stock: patch then resume
            asyncio.get_event_loop().create_task(
                self._patch_and_resume(session_id, target_type)
            )

    async def _patch_and_resume(self, session_id: str, target_type: str) -> None:
        """Inject stealth into new OOPIF/Worker, then resume."""
        try:
            session = self._get_session(session_id)
            if target_type == "iframe":
                await self.apply_to_session(session, is_oopif=True)
            # Resume execution
            await session.send("Runtime.runIfWaitingForDebugger", {})
        except Exception:
            logger.debug("Failed to patch target %s", session_id, exc_info=True)

    async def _resume_target(self, session_id: str) -> None:
        try:
            await self._get_session(session_id).send("Runtime.runIfWaitingForDebugger", {})
        except Exception:
            pass

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
        """Build the list of JS scripts for the extension."""
        if "native_fingerprint" in self._caps:
            return []

        p = self._profile
        scripts = [
            load_script("webdriver.js"),
            load_script("chrome_runtime.js"),
            load_script("plugins.js"),
            load_script("webgl.js", {
                "VENDOR": p.webgl_vendor,
                "RENDERER": p.webgl_renderer,
            }),
            load_script("navigator_proto.js", {
                "HARDWARE_CONCURRENCY": str(p.hardware_concurrency),
                "DEVICE_MEMORY": str(p.device_memory),
                "PLATFORM": p.platform,
            }),
            load_script("tostring_mask.js"),
            load_script("keyboard_layout.js", {
                "LOCALE": p.locale,
            }),
        ]

        if self._has_proxy:
            scripts.append(load_script("webrtc.js"))

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

    async def _apply_headless_fixes(self, session) -> None:
        """Apply headless-specific CDP fixes."""
        p = self._profile
        await session.send("Emulation.setFocusEmulationEnabled", {"enabled": True})
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
