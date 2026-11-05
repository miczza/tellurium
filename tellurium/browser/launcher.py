"""Chrome browser launcher: find, download (CfT), build flags, and launch with pipe FDs."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from tellurium.browser._cache import _version_key
from tellurium.browser.chrome_version import detect_chrome_version

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

    def version(entry: Path) -> tuple[int, ...]:
        return _version_key(entry.name.removeprefix("chrome-"))

    for entry in sorted(base.iterdir(), key=version, reverse=True):  # newest first
        if not entry.is_dir() or entry.name.startswith("."):  # skip staging dirs
            continue
        # Linux / macOS binary names
        for candidate in (
            entry / "chrome",
            entry / "chrome-linux64" / "chrome",
            entry
            / "chrome-mac-x64"
            / "Google Chrome for Testing.app"
            / "Contents"
            / "MacOS"
            / "Google Chrome for Testing",
            entry
            / "chrome-mac-arm64"
            / "Google Chrome for Testing.app"
            / "Contents"
            / "MacOS"
            / "Google Chrome for Testing",
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
        # Same priority as the other platforms: Chromium before branded
        # Chrome, because Chrome >= 137 dropped --load-extension.
        win_apps = [
            (r"Chromium\Application\chrome.exe", "chromium"),
            (r"Google\Chrome\Application\chrome.exe", "chrome"),
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
            version = await asyncio.to_thread(detect_chrome_version, path)
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


def _extract_zip(zip_path: Path, dest: Path) -> None:
    """Extract *zip_path* into *dest*, keeping Unix modes and symlinks.

    ``zipfile.extractall`` drops both: helpers such as
    ``chrome_crashpad_handler`` lose their exec bit and the macOS framework
    links become text files. Entries that would land outside *dest*
    (``..``, absolute paths, paths through a symlink) and symlinks pointing
    outside it are refused.
    """
    root = dest.resolve()
    links: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = Path(info.filename)
            parent = (root / name).parent.resolve()
            if name.is_absolute() or ".." in name.parts or not parent.is_relative_to(root):
                raise ValueError(f"Archive entry outside the install dir: {info.filename}")
            target = parent / name.name
            mode = info.external_attr >> 16
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(target):
                target.unlink()
            if stat.S_ISLNK(mode):
                link = zf.read(info).decode()
                if os.path.isabs(link):
                    raise ValueError(f"Archive link outside the install dir: {info.filename}")
                os.symlink(link, target)
                links.append(target)
                continue
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            if mode & 0o777:
                target.chmod(mode & 0o777)
    # Checked once every link exists: the kernel resolves a link before a
    # following '..', so a chain of links can climb out of a lexical check.
    for target in links:
        if not Path(os.path.realpath(target)).is_relative_to(root):
            raise ValueError(f"Archive link outside the install dir: {target.relative_to(root)}")


async def download_cft(version: str = "latest") -> str:
    """Download Chrome for Testing and return the path to its executable.

    *version* is a version string (e.g. ``"124.0.6367.60"``) or ``"latest"``;
    the archive is extracted to ``~/.tellurium/browsers/chrome-{version}/``.
    """
    # Network, unzip and chmod: all blocking, so off the event loop.
    return await asyncio.to_thread(_download_cft_sync, version)


def _download_cft_sync(version: str) -> str:
    import json as _json
    import urllib.request

    plat = _determine_platform()
    logger.info("Downloading Chrome for Testing (platform=%s, version=%s)", plat, version)

    # Resolve "latest" via the CfT JSON endpoint
    if version == "latest":
        api_url = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
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

    base = _tellurium_browsers_dir()
    base.mkdir(parents=True, exist_ok=True)
    dest_dir = base / f"chrome-{version}"
    # Download and extract in a hidden staging dir, then rename: a failure
    # never leaves a half-extracted install for _find_cft_managed to pick.
    staging = Path(tempfile.mkdtemp(prefix=f".chrome-{version}-", dir=base))
    try:
        zip_path = staging / f"chrome-{plat}.zip"
        logger.info("Downloading %s -> %s", download_url, zip_path)
        urllib.request.urlretrieve(download_url, zip_path)  # noqa: S310
        tree = staging / "tree"
        _extract_zip(zip_path, tree)
        app = Path(f"chrome-{plat}", "Google Chrome for Testing.app", "Contents", "MacOS")
        for rel in (
            Path("chrome"),
            Path(f"chrome-{plat}", "chrome"),
            app / "Google Chrome for Testing",
            Path(f"chrome-{plat}", "chrome.exe"),
        ):
            if (tree / rel).is_file():
                (tree / rel).chmod((tree / rel).stat().st_mode | 0o111)
                break
        else:
            raise FileNotFoundError(f"No Chrome binary in the archive from {download_url}")
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        os.replace(tree, dest_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    logger.info("Chrome for Testing ready at %s", dest_dir / rel)
    return str(dest_dir / rel)


def build_chrome_flags(
    *,
    headless: bool,
    user_data_dir: str,
    proxy: str | None,
    extra_args: list[str] | None,
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


# ---------------------------------------------------------------------------
# Windows launch
# ---------------------------------------------------------------------------

# Flags from the MSVC CRT (internal/ioinit.cpp): a handle entry is only
# adopted when FOPEN is set; FPIPE tells the CRT the handle is a pipe.
_CRT_FOPEN = 0x01
_CRT_FPIPE = 0x08

#: ``INVALID_HANDLE_VALUE`` — the placeholder for an fd slot the child must
#: resolve itself (the CRT falls back to ``GetStdHandle`` for fds 0/1/2).
_INVALID_HANDLE_VALUE = -1


def build_crt_inherit_block(handles: list[int | None], handle_size: int = 8) -> bytes:
    """Encode the MSVC CRT ``STARTUPINFO.lpReserved2`` inheritance block.

    Windows' ``CreateProcess`` can only pass three handles explicitly
    (stdin/stdout/stderr).  Every other inherited handle reaches the child as a
    bare HANDLE with no file-descriptor number — but Chrome's
    ``--remote-debugging-pipe`` reads the pipe through ``_get_osfhandle(3)`` /
    ``_get_osfhandle(4)``, i.e. it expects *CRT file descriptors* 3 and 4.

    The only mechanism that populates a child's CRT fd table is the
    undocumented block the MSVC runtime reads from ``lpReserved2`` (the same
    one libuv/Node write, which is how Puppeteer's pipe transport works on
    Windows).  Its layout is::

        int   count;               // number of fd slots
        char  flags[count];        // per-fd CRT flags
        HANDLE osfhnd[count];      // per-fd OS handle (pointer-sized)

    *handles* is indexed by file descriptor; ``None`` marks an unused slot.
    *handle_size* is the child's pointer size (8 on win64, 4 on win32).
    """
    count = len(handles)
    flags = bytearray()
    raw = bytearray()
    mask = (1 << (handle_size * 8)) - 1
    for handle in handles:
        if handle is None:
            flags.append(0)
            raw += (_INVALID_HANDLE_VALUE & mask).to_bytes(handle_size, "little")
        else:
            flags.append(_CRT_FOPEN | _CRT_FPIPE)
            raw += (handle & mask).to_bytes(handle_size, "little")
    return count.to_bytes(4, "little") + bytes(flags) + bytes(raw)


def launch_chrome_windows(
    chrome_path: str,
    args: list[str],
) -> tuple[object, int, int]:
    """Launch Chrome with CDP pipe handles on Windows.

    **Untested on real Windows** — Tellurium's CI and development machines are
    POSIX only.  The logic is covered by unit tests that fake ``sys.platform``
    and the Win32 entry points (``tests/unit/test_launcher_windows.py``); the
    end-to-end behaviour against a real ``chrome.exe`` has never been observed.
    Treat a failure here as a bug report, not as a supported path.

    Mirrors :func:`~tellurium.browser.process.launch_chrome_posix`: two anonymous pipes are created, the
    child ends are handed over as file descriptors 3 (Chrome reads) and 4
    (Chrome writes), and the parent ends are returned as CRT file descriptors
    ready for :class:`~tellurium.cdp.transport._pipe_win.PipeWindowsTransport`.

    ``subprocess.Popen`` is bypassed on purpose: it can only pass handles for
    fds 0-2, and ``STARTUPINFO.lpAttributeList["handle_list"]`` makes a handle
    *inheritable* without giving it an fd number in the child.  Chrome needs
    real CRT fds 3/4, so the process is created through ``CreateProcessW``
    with the CRT block from :func:`build_crt_inherit_block` in ``lpReserved2``.

    Returns ``(process, parent_write_fd, parent_read_fd)`` where *process* is a
    small ``Popen``-compatible wrapper exposing ``pid``/``poll``/``wait``/
    ``terminate``/``kill``.
    """
    if sys.platform != "win32":  # pragma: no cover - guarded by the dispatcher
        raise RuntimeError("launch_chrome_windows() is Windows-only; use process.launch_chrome().")
    import _winapi
    import ctypes
    import ctypes.wintypes as wintypes
    import msvcrt

    class _STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(ctypes.c_ubyte)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class _PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    # CreatePipe() in CPython returns *inheritable* handles; only the two the
    # child must see may stay that way, otherwise the child keeps the parent's
    # ends open and the pipe never reports EOF.
    chrome_read_h, parent_write_h = _winapi.CreatePipe(None, 0)
    parent_read_h, chrome_write_h = _winapi.CreatePipe(None, 0)
    os.set_handle_inheritable(parent_write_h, False)
    os.set_handle_inheritable(parent_read_h, False)
    os.set_handle_inheritable(chrome_read_h, True)
    os.set_handle_inheritable(chrome_write_h, True)

    # fds 0/1/2 are left unset: the CRT resolves them from the std handles.
    block = build_crt_inherit_block(
        [None, None, None, chrome_read_h, chrome_write_h],
        handle_size=ctypes.sizeof(ctypes.c_void_p),
    )
    buffer = (ctypes.c_ubyte * len(block)).from_buffer_copy(block)

    startup = _STARTUPINFOW()
    startup.cb = ctypes.sizeof(_STARTUPINFOW)
    startup.cbReserved2 = len(block)
    startup.lpReserved2 = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))

    info = _PROCESS_INFORMATION()
    command_line = subprocess.list2cmdline([chrome_path, *args])
    created = ctypes.windll.kernel32.CreateProcessW(
        ctypes.c_wchar_p(chrome_path),
        ctypes.c_wchar_p(command_line),
        None,  # process security attributes
        None,  # thread security attributes
        True,  # bInheritHandles — required for the two pipe ends
        0,  # dwCreationFlags
        None,  # environment (inherit)
        None,  # current directory (inherit)
        ctypes.byref(startup),
        ctypes.byref(info),
    )
    if not created:
        for handle in (chrome_read_h, chrome_write_h, parent_read_h, parent_write_h):
            _winapi.CloseHandle(handle)
        raise OSError(ctypes.GetLastError(), f"CreateProcessW failed for {chrome_path}")

    _winapi.CloseHandle(info.hThread)
    # The child owns its ends now.
    _winapi.CloseHandle(chrome_read_h)
    _winapi.CloseHandle(chrome_write_h)

    # Hand the parent ends to the transport as CRT file descriptors; the fd
    # now owns the handle, so it must not be closed separately.
    parent_write_fd = msvcrt.open_osfhandle(parent_write_h, 0)
    parent_read_fd = msvcrt.open_osfhandle(parent_read_h, os.O_RDONLY)

    return _WindowsProcess(info.hProcess, info.dwProcessId), parent_write_fd, parent_read_fd


class _WindowsProcess:
    """Minimal ``subprocess.Popen`` stand-in around a raw process handle.

    Only the surface ``Browser.close()`` uses is implemented.  **Untested on
    real Windows.**
    """

    def __init__(self, handle: int, pid: int):
        self._handle = handle
        self.pid = pid
        self.returncode: int | None = None

    def poll(self) -> int | None:
        import _winapi

        if self.returncode is None:
            if _winapi.WaitForSingleObject(self._handle, 0) == 0:  # WAIT_OBJECT_0
                self.returncode = _winapi.GetExitCodeProcess(self._handle)
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        import _winapi

        if self.returncode is None:
            ms = 0xFFFFFFFF if timeout is None else int(timeout * 1000)
            if _winapi.WaitForSingleObject(self._handle, ms) != 0:
                raise subprocess.TimeoutExpired("chrome", timeout)
            self.returncode = _winapi.GetExitCodeProcess(self._handle)
        return self.returncode

    def terminate(self) -> None:
        import ctypes

        if self.returncode is None:
            ctypes.windll.kernel32.TerminateProcess(self._handle, 1)

    kill = terminate


def __getattr__(name: str):
    """Old import paths: process spawning moved to :mod:`tellurium.browser.process`."""
    if name in ("launch_chrome", "launch_chrome_posix"):
        from tellurium.browser import process

        return getattr(process, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
