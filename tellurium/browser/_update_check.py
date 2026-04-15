"""Silent daily update check for tellurium-chromium.

Runs at most once per day, caches the result in ~/.tellurium/.update-check.
Emits WARNING logs if the installed version is >12 weeks old or if a
security release is available. Never auto-installs (opt-in via
Browser.launch(auto_security_update=True)).
"""
from __future__ import annotations
import json
import logging
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("tellurium")

_MANIFEST_URL = (
    "https://github.com/tellurium-browser/tellurium-chromium/releases/"
    "latest/download/MANIFEST.json"
)
_CHECK_INTERVAL = timedelta(hours=24)
_STALE_THRESHOLD = timedelta(weeks=12)


def check_for_update(
    *,
    cache_root: Path,
    check_file: Path | None = None,
    url: str = _MANIFEST_URL,
) -> None:
    """Silent daily update check. Emits WARNING if stale or security release."""
    if check_file is None:
        check_file = cache_root.parent / ".update-check"
    now = datetime.now(timezone.utc)

    # Skip if checked < 24h ago
    if check_file.exists():
        try:
            cached = json.loads(check_file.read_text())
            last = datetime.fromisoformat(cached["last_check"])
            if now - last < _CHECK_INTERVAL:
                return
        except (json.JSONDecodeError, KeyError, ValueError):
            pass   # re-check

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            manifest = json.loads(resp.read())
    except Exception as e:
        log.debug("Update check failed (silent): %s", e)
        return

    check_file.parent.mkdir(parents=True, exist_ok=True)
    check_file.write_text(json.dumps({
        "last_check": now.isoformat(),
        "latest_version": manifest.get("version", ""),
    }))

    installed = _installed_version(cache_root)
    latest = manifest.get("version", "")
    if not latest or installed == latest:
        return

    released_at = manifest.get("released_at")
    try:
        age = now - datetime.fromisoformat(released_at)
    except Exception:
        age = timedelta(0)

    if manifest.get("security"):
        cve = ", ".join(manifest.get("cve", []))
        severity = manifest.get("severity", "unknown")
        log.warning(
            "tellurium-chromium %s installed — SECURITY release %s available "
            "(severity: %s, CVE: %s). Run `tellurium update-browser --security-only`.",
            installed, latest, severity, cve,
        )
    else:
        # age is how long the newer version has been available — a lower bound
        # on how old the installed version is.  Warn whenever the binary is
        # behind; the week count gives the user a sense of urgency.
        weeks = max(1, int(age.total_seconds() / (7 * 24 * 3600)))
        if age >= _STALE_THRESHOLD:
            # Long-overdue update — stronger nudge
            log.warning(
                "tellurium-chromium %s is %d weeks old. Latest: %s. "
                "Run `tellurium update-browser` to upgrade.",
                installed, weeks, latest,
            )
        else:
            log.warning(
                "tellurium-chromium %s is at least %d weeks old. Latest: %s. "
                "Run `tellurium update-browser` to upgrade.",
                installed, weeks, latest,
            )


def _installed_version(cache_root: Path) -> str:
    current = cache_root / "current"
    if current.is_symlink():
        return current.resolve().name
    return ""
