"""The Chrome process and everything a launch creates around it.

:class:`BrowserProcess` owns the proxy forwarder, the temporary profile and
downloads folder, the Chrome process, its output sink and the CDP pipe transport, and releases them
in a safe order whether the launch succeeded, failed or was cancelled.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from tellurium.browser.launcher import LaunchError, launch_chrome_windows
from tellurium.cdp.transport import create_transport
from tellurium.cdp.transport._base import CDPTransport

logger = logging.getLogger("tellurium")

#: How much of Chrome's latest output is kept to explain a failed launch.
OUTPUT_TAIL_BYTES = 8192

#: Lowest fd the child's pipe ends are parked on before landing on 3 and 4.
_PARK_FD = 10

#: How long Chrome gets to exit on its own after ``Browser.close``, before the signals.
CLOSE_GRACE = 5.0

#: ``Browser.close`` with an id the session router never hands out (it counts
#: up from 0); its reply, if any, matches no pending command and is dropped.
_BROWSER_CLOSE = json.dumps({"id": 2**31 - 1, "method": "Browser.close"}).encode() + b"\0"


def launch_chrome_posix(
    chrome_path: str,
    args: list[str],
    output: int = subprocess.DEVNULL,
    env: dict[str, str] | None = None,
) -> tuple[subprocess.Popen, int, int]:
    """Launch Chrome with CDP pipe FDs (POSIX only).

    Creates two anonymous pipes and remaps them to file descriptors 3 (read
    by Chrome) and 4 (written by Chrome) in the child, as
    ``--remote-debugging-pipe`` expects. Chrome's stdout and stderr go to
    *output* (an fd, or ``subprocess.DEVNULL``): never to a pipe nobody reads,
    which freezes Chrome once 64 KiB of log pile up. *env* replaces the
    environment when given.

    Returns ``(process, parent_write_fd, parent_read_fd)``.
    """
    chrome_read_fd, parent_write_fd = os.pipe()  # parent writes -> chrome reads on fd 3
    parent_read_fd, chrome_write_fd = os.pipe()  # chrome writes on fd 4 -> parent reads

    def _remap_fds() -> None:
        """Runs in the child before exec.

        Any of the four ends can sit on 3 or 4 (an embedder with few open
        fds), so the parent's ends are closed first and the child's ends are
        parked above 4: no ``dup2`` can then clobber an end still needed.
        """
        import fcntl

        os.close(parent_write_fd)
        os.close(parent_read_fd)
        parked_read = fcntl.fcntl(chrome_read_fd, fcntl.F_DUPFD, _PARK_FD)
        parked_write = fcntl.fcntl(chrome_write_fd, fcntl.F_DUPFD, _PARK_FD)
        os.dup2(parked_read, 3)
        os.dup2(parked_write, 4)
        for fd in {parked_read, parked_write, chrome_read_fd, chrome_write_fd} - {3, 4}:
            os.close(fd)

    try:
        process = subprocess.Popen(
            [chrome_path, *args],
            preexec_fn=_remap_fds,
            close_fds=False,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            env=env,
        )
    except BaseException:
        for fd in (chrome_read_fd, chrome_write_fd, parent_read_fd, parent_write_fd):
            os.close(fd)
        raise
    # The child has its own copies now.
    os.close(chrome_read_fd)
    os.close(chrome_write_fd)
    return process, parent_write_fd, parent_read_fd


def launch_chrome(
    chrome_path: str,
    args: list[str],
    output: int = subprocess.DEVNULL,
    env: dict[str, str] | None = None,
) -> tuple[Any, int, int]:
    """Launch Chrome with CDP pipes using the current platform's mechanism.

    Returns ``(process, parent_write_fd, parent_read_fd)``. *output* and
    *env* are not supported on Windows yet: Chrome keeps the parent's
    standard handles and environment.
    """
    if sys.platform == "win32":
        return launch_chrome_windows(chrome_path, args)
    return launch_chrome_posix(chrome_path, args, output, env)


class OutputTail:
    """Drains Chrome's output on a thread, keeping only the last bytes.

    A thread, not the event loop: Chrome blocks as soon as its output pipe is
    full, so the pipe must keep draining while the loop is busy.
    """

    def __init__(self, read_fd: int) -> None:
        self._fd = read_fd
        self._tail = bytearray()
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._drain, name="tellurium-chrome-output", daemon=True
        )
        self._thread.start()

    def _drain(self) -> None:
        try:
            while chunk := os.read(self._fd, 65536):
                with self._lock:
                    self._tail += chunk
                    del self._tail[:-OUTPUT_TAIL_BYTES]
        except OSError:
            pass
        finally:
            os.close(self._fd)

    def join(self, timeout: float) -> None:
        """Wait for EOF (every Chrome process gone), at most *timeout* seconds."""
        self._thread.join(timeout)

    def text(self) -> str:
        with self._lock:
            return self._tail.decode(errors="replace")


def _file_tail(path: Path) -> str:
    try:
        with open(path, "rb") as log:
            log.seek(max(0, log.seek(0, os.SEEK_END) - OUTPUT_TAIL_BYTES))
            return log.read().decode(errors="replace")
    except OSError:
        return ""


class BrowserProcess:
    """Owner of every resource a launch creates.

    Each resource is recorded as soon as it exists, so :meth:`close` releases
    exactly what was created, whatever step the launch reached.
    """

    def __init__(self) -> None:
        self.process: Any = None
        self.reader: asyncio.Task | None = None  # the task dispatching CDP messages
        self.transport: CDPTransport | None = None
        self.forwarder: Any = None
        self.temp_profile: str | None = None
        self.chrome_tmp: str | None = None  # Chrome's TMPDIR
        self.downloads_tmp: str | None = None  # default downloads folder
        self.headless = False  # whether the flags Chrome got make it headless
        self._output: OutputTail | None = None
        self._log_path: Path | None = None
        self._log_file: Any = None

    async def start_forwarder(self, forwarder: Any) -> None:
        self.forwarder = forwarder
        await forwarder.start()

    def make_temp_profile(self) -> str:
        self.temp_profile = tempfile.mkdtemp(prefix="tellurium_")
        return self.temp_profile

    def make_downloads_dir(self) -> str:
        self.downloads_tmp = tempfile.mkdtemp(prefix="tellurium_dl_")
        return self.downloads_tmp

    async def spawn(
        self, chrome_path: str, flags: list[str], chrome_log: Path | None
    ) -> CDPTransport:
        """Start Chrome and connect its CDP pipe.

        Chrome's output goes to *chrome_log* when given; otherwise it is
        drained and only its tail is kept, to explain a failed launch.
        Chrome's TMPDIR is a directory of ours, removed by :meth:`close`:
        it leaves shared-memory files and its singleton socket there.
        """
        self.headless = any(f == "--headless" or f.startswith("--headless=") for f in flags)
        self.chrome_tmp = tempfile.mkdtemp(prefix="tellurium_tmp_")
        env = {**os.environ, "TMPDIR": self.chrome_tmp}
        output, tail_fd = subprocess.DEVNULL, None
        if chrome_log is not None:
            if sys.platform == "win32":
                logger.warning("chrome_log is not supported on Windows yet; ignoring it")
            else:
                self._log_path = Path(chrome_log)
                self._log_file = open(self._log_path, "ab")  # noqa: SIM115 - owned, closed in close()
                output = self._log_file.fileno()
        elif sys.platform != "win32":
            tail_fd, output = os.pipe()
        try:
            self.process, write_fd, read_fd = launch_chrome(chrome_path, flags, output, env)
            # The transport owns both pipe ends from here on.
            self.transport = create_transport(read_fd, write_fd)
            if tail_fd is not None:
                self._output = OutputTail(tail_fd)
        except BaseException:
            if tail_fd is not None and self._output is None:
                os.close(tail_fd)
            raise
        finally:
            if tail_fd is not None:
                os.close(output)
        await self.transport.start()
        return self.transport

    async def launch_error(self, cause: BaseException) -> LaunchError | None:
        """Explain a launch that failed because Chrome exited on its own.

        Returns ``None`` when Chrome is still running: then *cause* is the
        real error. A closed pipe means Chrome is exiting, so its exit is
        awaited briefly before deciding.
        """
        if self.process is None or not isinstance(cause, Exception):
            return None
        grace = 2.0 if isinstance(cause, (ConnectionError, EOFError)) else 0.0
        try:
            code = await asyncio.to_thread(self.process.wait, grace)
        except subprocess.TimeoutExpired:
            return None
        output = await self._output_tail()
        message = f"Chrome exited during launch (exit code {code})"
        if output.strip():
            message += f". Its last output:\n{output.strip()}"
        return LaunchError(message)

    async def _output_tail(self) -> str:
        if self._output is not None:
            await asyncio.to_thread(self._output.join, 2.0)
            return self._output.text()
        if self._log_path is not None:
            if self._log_file is not None:
                self._log_file.flush()
            return await asyncio.to_thread(_file_tail, self._log_path)
        return ""

    async def close(self) -> None:
        """Stop Chrome, then release its pipe, output, forwarder and temp folders.

        Chrome is first asked to close over CDP (``Browser.close``, the
        orderly exit that writes the cookie store) and given
        :data:`CLOSE_GRACE` seconds; then SIGTERM, then SIGKILL. The CDP
        reader keeps draining the pipe meanwhile, so Chrome never blocks on it.
        Chrome is stopped *before* its pipe is closed: on Windows, closing a
        pipe handle with a read pending on it can block until Chrome exits.
        Every step runs, even when an earlier one fails or the caller is
        cancelled (again and again, e.g. during a launch rollback); each is
        bounded by a timeout. A cancellation is re-raised once all are done.
        Safe to call more than once.
        """
        cancelled = False
        if self.process is not None and self.transport is not None:
            cancelled |= await _settle(
                "ask Chrome to close", self._ask_to_close(), timeout=CLOSE_GRACE + 2
            )
        if self.reader is not None:
            reader, self.reader = self.reader, None
            reader.cancel()
            cancelled |= await _settle("stop the CDP reader", asyncio.wait([reader]))
        if self.process is not None:
            cancelled |= await _settle("stop Chrome", asyncio.to_thread(_stop, self.process))
        if self.transport is not None:
            transport, self.transport = self.transport, None
            cancelled |= await _settle("close the CDP pipe", transport.close())
        if self._output is not None:
            output, self._output = self._output, None
            cancelled |= await _settle("drain Chrome output", asyncio.to_thread(output.join, 5.0))
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None
        if self.forwarder is not None:
            forwarder, self.forwarder = self.forwarder, None
            cancelled |= await _settle("stop the proxy forwarder", forwarder.stop())
        for attr in ("temp_profile", "chrome_tmp", "downloads_tmp"):
            path = getattr(self, attr)
            if path is not None:
                setattr(self, attr, None)
                removal = asyncio.to_thread(shutil.rmtree, path, ignore_errors=True)
                cancelled |= await _settle(f"remove {path}", removal)
        if cancelled:
            raise asyncio.CancelledError

    async def _ask_to_close(self) -> None:
        """Send ``Browser.close`` and wait (at most :data:`CLOSE_GRACE`) for Chrome to exit.

        Skipped when Chrome is gone or nobody reads the pipe any more (no
        reader, or it ended: the pipe is broken); a failed send just leaves
        the signals to do it.
        """
        process = self.process
        if process.poll() is not None or self.reader is None or self.reader.done():
            return
        try:
            await asyncio.wait_for(self.transport.send(_BROWSER_CLOSE), 1.0)
        except (OSError, ConnectionError, asyncio.TimeoutError) as exc:
            logger.debug("Could not send Browser.close: %s", exc)
            return
        try:
            await asyncio.to_thread(process.wait, CLOSE_GRACE)
        except subprocess.TimeoutExpired:
            logger.debug("Chrome ignored Browser.close for %.0f s; signalling it", CLOSE_GRACE)


async def _settle(what: str, awaitable: Any, timeout: float = 15.0) -> bool:
    """Drive *awaitable* to its end (bounded by *timeout*) across cancellations.

    Returns whether the caller was cancelled meanwhile, so it can finish its
    other cleanup steps first and re-raise afterwards. Failures are logged.
    """
    step = asyncio.ensure_future(asyncio.wait_for(awaitable, timeout))
    cancelled = False
    while not step.done():
        try:
            await asyncio.shield(step)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:  # noqa: BLE001 - logged below
            break
    if not step.cancelled() and step.exception() is not None:
        logger.warning("Could not %s", what, exc_info=step.exception())
    return cancelled


def _stop(process: Any) -> None:
    """Terminate *process* and reap it; kill it if it ignores SIGTERM."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
