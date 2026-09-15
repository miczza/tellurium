"""Silent daily update check for chromium-telluride.

Runs at most once per day, caches the result in ~/.tellurium/.update-check.
Emits WARNING logs if the installed version is behind the latest release or
if a security release is available. Never auto-installs by itself: the
caller (``PatchedEngine``) decides based on ``auto_security_update``.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from tellurium.browser import _cache

log = logging.getLogger("tellurium")

GITHUB_REPO = "miczza/chromium-telluride"
MANIFEST_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/MANIFEST.json"
_MANIFEST_URL = MANIFEST_URL  # backwards-compatible alias
_CHECK_INTERVAL = timedelta(hours=24)
_STALE_THRESHOLD = timedelta(weeks=12)


@dataclass(frozen=True)
class UpdateInfo:
    installed: str | None
    latest: str            # install-dir name (chromium upstream version)
    manifest: dict[str, Any]

    @property
    def available(self) -> bool:
        return bool(self.latest) and self.installed != self.latest

    @property
    def security(self) -> bool:
        return self.available and bool(self.manifest.get("security"))


def _latest_dir_name(manifest: dict[str, Any]) -> str:
    return manifest.get("chromium_upstream") or manifest.get("version", "")


def check_for_update(
    *,
    cache_root: Path,
    check_file: Path | None = None,
    url: str = MANIFEST_URL,
    force: bool = False,
) -> UpdateInfo | None:
    """Silent daily update check.

    Returns :class:`UpdateInfo` when a manifest was fetched (whether or not an
    update is available), ``None`` when the check was skipped or failed.
    """
    if check_file is None:
        check_file = _cache.update_check_file(cache_root)
    now = datetime.now(timezone.utc)

    if not force and check_file.exists():
        try:
            cached = json.loads(check_file.read_text())
            last = datetime.fromisoformat(cached["last_check"])
            if now - last < _CHECK_INTERVAL:
                return None
        except (json.JSONDecodeError, KeyError, ValueError):
            pass   # re-check

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            manifest = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001 - network failures are silent by design
        log.debug("Update check failed (silent): %s", e)
        return None

    check_file.parent.mkdir(parents=True, exist_ok=True)
    # Not locked: concurrent launches may both fetch; worst case is one extra HTTP
    # request per race window + a torn write that triggers a re-check next run.
    check_file.write_text(json.dumps({
        "last_check": now.isoformat(),
        "latest_version": _latest_dir_name(manifest),
    }))

    installed = _cache.installed_version(cache_root)
    info = UpdateInfo(installed=installed, latest=_latest_dir_name(manifest), manifest=manifest)
    if not info.available:
        return info

    released_at = manifest.get("released_at")
    try:
        age = now - datetime.fromisoformat(str(released_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        age = timedelta(0)

    if info.security:
        cve = ", ".join(manifest.get("cve", []))
        severity = manifest.get("severity", "unknown")
        log.warning(
            "chromium-telluride %s installed — SECURITY release %s available "
            "(severity: %s, CVE: %s). Run `tellurium update-browser --security-only`.",
            installed, info.latest, severity, cve,
        )
    else:
        # age = how long the newer version has been available — lower bound
        # on how stale the installed binary is. Warn whenever installed is behind.
        weeks = max(1, int(age.total_seconds() / (7 * 24 * 3600)))
        qualifier = "" if age >= _STALE_THRESHOLD else "at least "
        log.warning(
            "chromium-telluride %s is %s%d weeks old. Latest: %s. "
            "Run `tellurium update-browser` to upgrade.",
            installed, qualifier, weeks, info.latest,
        )
    return info


def _installed_version(cache_root: Path) -> str:
    return _cache.installed_version(cache_root) or ""
