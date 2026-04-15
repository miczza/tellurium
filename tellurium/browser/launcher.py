"""Chrome browser launcher: find, download (CfT), build flags, and launch with pipe FDs."""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base flags applied to every Chrome launch
# ---------------------------------------------------------------------------

BASE_FLAGS = [
    "--remote-debugging-pipe",
    "--no-first-run",
    "--no-default-browser-check",
    "--no-service-autorun",
    "--disable-breakpad",
    "--disable-dev-shm-usage",
    "--disable-infobars",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)\.(\d+)")


def _detect_chrome_version(executable: str) -> Optional[tuple[int, ...]]:
    """Run *executable* --version and return a 4-tuple of ints, or None on failure."""
    try:
        output = subprocess.check_output(
            [executable, "--version"],
            stderr=subprocess.STDOUT,
            timeout=5,
        )
        text = output.decode(errors="replace")
        m = _VERSION_RE.search(text)
        if m:
            return tuple(int(x) for x in m.groups())
    except Exception:
        pass
    return None


def _determine_platform() -> str:
    """Return the Chrome for Testing platform string for the current host."""
    machine = platform.machine()
    if sys.platform.startswith("linux"):
        if machine in ("aarch64", "arm64"):
            return "linux-arm64"
        return "linux64"
    if sys.platform == "darwin":
        if machine == "arm64":
            return "mac-arm64"
        return "mac-x64"
    if sys.platform == "win32":
        if machine in ("AMD64", "x86_64"):
            return "win64"
        return "win32"
    return "linux64"  # fallback


def _tellurium_browsers_dir() -> Path:
    """~/.tellurium/browsers/"""
    return Path.home() / ".tellurium" / "browsers"


def _find_cft_managed() -> list[tuple[str, str]]:
    """Return [(path, 'cft')] for any Chrome for Testing installs managed by Tellurium."""
    results: list[tuple[str, str]] = []
    base = _tellurium_browsers_dir()
    if not base.is_dir():
        return results

    for entry in sorted(base.iterdir(), reverse=True):  # newest version first
        if not entry.is_dir():
            continue
        # Linux / macOS binary names
        for candidate in (
            entry / "chrome",
            entry / "chrome-linux64" / "chrome",
            entry / "chrome-mac-x64" / "Google Chrome for Testing.app"
            / "Contents" / "MacOS" / "Google Chrome for Testing",
            entry / "chrome-mac-arm64" / "Google Chrome for Testing.app"
            / "Contents" / "MacOS" / "Google Chrome for Testing",
            entry / "chrome-win64" / "chrome.exe",
            entry / "chrome-win32" / "chrome.exe",
        ):
            if candidate.is_file():
                results.append((str(candidate), "cft"))
                break
    return results


def _find_chrome_candidates() -> list[tuple[str, str]]:
    """Return a prioritised list of (path, kind) Chrome candidates.

    Priority: CfT managed > chromium > chrome > edge > brave.
    """
    candidates: list[tuple[str, str]] = []

    # --- Tellurium-managed CfT installs (highest priority) ---
    candidates.extend(_find_cft_managed())

    if sys.platform.startswith("linux"):
        _which_pairs = [
            ("chromium", "chromium"),
            ("chromium-browser", "chromium"),
            ("google-chrome", "chrome"),
            ("google-chrome-stable", "chrome"),
            ("microsoft-edge", "edge"),
            ("brave-browser", "brave"),
        ]
        for name, kind in _which_pairs:
            path = shutil.which(name)
            if path:
                candidates.append((path, kind))

    elif sys.platform == "darwin":
        app_paths = [
            ("/Applications/Chromium.app/Contents/MacOS/Chromium", "chromium"),
            ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "chrome"),
            (
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "edge",
            ),
            (
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "brave",
            ),
        ]
        for path, kind in app_paths:
            if Path(path).is_file():
                candidates.append((path, kind))

    elif sys.platform == "win32":
        pf_dirs = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        win_apps = [
            (r"Google\Chrome\Application\chrome.exe", "chrome"),
            (r"Chromium\Application\chrome.exe", "chromium"),
            (r"Microsoft\Edge\Application\msedge.exe", "edge"),
            (r"BraveSoftware\Brave-Browser\Application\brave.exe", "brave"),
        ]
        for base in pf_dirs:
            if not base:
                continue
            for rel, kind in win_apps:
                full = Path(base) / rel
                if full.is_file():
                    candidates.append((str(full), kind))

    return candidates


# ---------------------------------------------------------------------------
# Extension helpers
# ---------------------------------------------------------------------------


class LaunchError(RuntimeError):
    """Raised when browser launch cannot proceed due to configuration
    incompatibility (e.g., Chrome 137+ branded + extensions)."""


def validate_extension_paths(extensions: list[str]) -> None:
    """Validate each extension path is an unpacked directory with manifest.json.
    Raises ValueError on first invalid path."""
    for ext in extensions:
        p = Path(ext)
        if not p.is_dir():
            raise ValueError(
                f"Extension path must be an unpacked directory: {ext}. "
                f".crx files are not supported — unpack with `unzip ext.crx -d ext/`."
            )
        if not (p / "manifest.json").exists():
            raise ValueError(f"No manifest.json in {ext}")


def check_chrome_version_for_extensions(
    *,
    executable: str,
    version: tuple[int, ...] | None,
    is_branded_chrome: bool,
    extensions: list[str],
) -> None:
    """Raise LaunchError if Chrome branded >= 137 is asked to load
    user extensions."""
    if not extensions:
        return
    if is_branded_chrome and version is not None and version[0] >= 137:
        raise LaunchError(
            f"Chrome {'.'.join(map(str, version))} at {executable} (branded) does not support "
            f"--load-extension since 137. Install Chrome for Testing or "
            f"Chromium to use extensions: `tellurium download-browser`."
        )


def build_load_extension_flag(
    *,
    tellurium_stealth_path: str | None,
    user_extensions: list[str],
) -> str:
    if not tellurium_stealth_path and not user_extensions:
        raise ValueError("build_load_extension_flag requires at least one path")
    paths: list[str] = []
    if tellurium_stealth_path:
        paths.append(tellurium_stealth_path)
    paths.extend(user_extensions)
    return f"--load-extension={','.join(paths)}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def find_chrome(stealth: bool = False) -> str:
    """Find a usable Chrome executable, downloading CfT as a last resort.

    Parameters
    ----------
    stealth:
        When True, branded Chrome >= 137 triggers a warning because Google's
        privacy sandbox changes can leak automation signals.

    Returns
    -------
    str
        Absolute path to the Chrome executable.

    Raises
    ------
    FileNotFoundError
        When no Chrome is found and the CfT download fails.
    """
    for path, kind in _find_chrome_candidates():
        logger.debug("Checking Chrome candidate: %s (%s)", path, kind)
        if stealth and kind == "chrome":
            version = _detect_chrome_version(path)
            if version and version[0] >= 137:
                logger.warning(
                    "Branded Chrome %d.%d.%d.%d (>= 137) detected at %s. "
                    "Google's privacy-sandbox changes may expose automation signals. "
                    "Consider using Chrome for Testing (stealth-safe).",
                    *version,
                    path,
                )
        return path

    logger.info("No Chrome found locally; downloading Chrome for Testing…")
    return await download_cft()


async def download_cft(version: str = "latest") -> str:
    """Download Chrome for Testing and return the path to its executable.

    The archive is extracted to ``~/.tellurium/browsers/chrome-{version}/``.

    Parameters
    ----------
    version:
        A specific version string (e.g. ``"124.0.6367.60"``) or ``"latest"``.

    Returns
    -------
    str
        Absolute path to the extracted Chrome executable.
    """
    try:
        import urllib.request
        import json as _json
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("stdlib urllib is unavailable") from exc

    plat = _determine_platform()
    logger.info("Downloading Chrome for Testing (platform=%s, version=%s)", plat, version)

    # Resolve "latest" via the CfT JSON endpoint
    if version == "latest":
        api_url = (
            "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
        )
        with urllib.request.urlopen(api_url, timeout=30) as resp:  # noqa: S310
            data = _json.loads(resp.read())
        version = data["channels"]["Stable"]["version"]
        download_url = None
        for entry in data["channels"]["Stable"]["downloads"].get("chrome", []):
            if entry["platform"] == plat:
                download_url = entry["url"]
                break
    else:
        download_url = (
            f"https://storage.googleapis.com/chrome-for-testing-public/"
            f"{version}/{plat}/chrome-{plat}.zip"
        )

    if not download_url:
        raise FileNotFoundError(
            f"No Chrome for Testing download found for platform={plat}, version={version}"
        )

    dest_dir = _tellurium_browsers_dir() / f"chrome-{version}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dest_dir / f"chrome-{plat}.zip"
    logger.info("Downloading %s -> %s", download_url, zip_path)
    urllib.request.urlretrieve(download_url, zip_path)  # noqa: S310

    logger.info("Extracting %s", zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    zip_path.unlink(missing_ok=True)

    # Locate the extracted binary
    for candidate in (
        dest_dir / "chrome",
        dest_dir / f"chrome-{plat}" / "chrome",
        dest_dir / f"chrome-{plat}" / "Google Chrome for Testing.app"
        / "Contents" / "MacOS" / "Google Chrome for Testing",
        dest_dir / f"chrome-{plat}" / "chrome.exe",
    ):
        if candidate.is_file():
            candidate.chmod(candidate.stat().st_mode | 0o111)
            logger.info("Chrome for Testing ready at %s", candidate)
            return str(candidate)

    raise FileNotFoundError(
        f"Could not locate Chrome binary inside extracted archive at {dest_dir}"
    )


def build_chrome_flags(
    *,
    headless: bool,
    user_data_dir: str,
    proxy: Optional[str],
    extra_args: Optional[list[str]],
    engine_args: list[str],
) -> list[str]:
    """Assemble the full Chrome CLI flag list.

    Parameters
    ----------
    headless:
        Launch in headless mode (``--headless=new``).
    user_data_dir:
        Path to the Chrome user-data directory.
    proxy:
        Proxy server string, e.g. ``"localhost:8080"``.  ``None`` means no proxy.
    extra_args:
        Additional flags to append verbatim.
    engine_args:
        Arguments forwarded from the stealth / fingerprint engine.

    Returns
    -------
    list[str]
        Ordered list of flags ready to be passed to Chrome.
    """
    flags: list[str] = list(BASE_FLAGS)

    flags.append(f"--user-data-dir={user_data_dir}")

    if headless:
        flags.append("--headless=new")

    if proxy:
        flags.append(f"--proxy-server={proxy}")

    if extra_args:
        flags.extend(extra_args)

    if engine_args:
        flags.extend(engine_args)

    return flags


def launch_chrome_posix(
    chrome_path: str,
    args: list[str],
) -> tuple[subprocess.Popen, int, int]:
    """Launch Chrome with CDP pipe FDs (POSIX only).

    Creates two anonymous pipes and remaps them to file descriptors 3 (read by
    Chrome) and 4 (written by Chrome) inside the child process, matching the
    ``--remote-debugging-pipe`` protocol.

    Parameters
    ----------
    chrome_path:
        Absolute path to the Chrome executable.
    args:
        CLI flags (should include ``--remote-debugging-pipe``).

    Returns
    -------
    (process, parent_write_fd, parent_read_fd)
        * **process** — the ``subprocess.Popen`` object
        * **parent_write_fd** — the parent's write end of the pipe (send CDP messages here)
        * **parent_read_fd** — the parent's read end of the pipe (receive CDP messages here)
    """
    # pipe(): (read_end, write_end)
    chrome_read_fd, parent_write_fd = os.pipe()   # parent writes -> chrome reads on fd 3
    parent_read_fd, chrome_write_fd = os.pipe()   # chrome writes on fd 4 -> parent reads

    def _remap_fds() -> None:
        """Called in the child process before exec."""
        if chrome_read_fd != 3:
            os.dup2(chrome_read_fd, 3)
            os.close(chrome_read_fd)
        if chrome_write_fd != 4:
            os.dup2(chrome_write_fd, 4)
            os.close(chrome_write_fd)
        os.close(parent_write_fd)
        os.close(parent_read_fd)

    process = subprocess.Popen(
        [chrome_path, *args],
        preexec_fn=_remap_fds,
        close_fds=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Close child-side FDs in the parent; they've been inherited by the child.
    os.close(chrome_read_fd)
    os.close(chrome_write_fd)

    return process, parent_write_fd, parent_read_fd
