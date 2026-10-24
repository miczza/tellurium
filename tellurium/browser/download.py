"""Downloads: where Chrome saves files and who is waiting for them.

Chrome saves every download under the folder of its browser context, named by
the download's GUID (``Browser.setDownloadBehavior`` with ``allowAndName``),
and reports it on the browser session with ``Browser.downloadWillBegin`` and
``Browser.downloadProgress``. :class:`Downloads` hands each new download to the
first :class:`DownloadWaiter` whose filter accepts the frame that started it.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

#: Default deadline of a waiter and of :meth:`Download.path`, in seconds.
DEFAULT_TIMEOUT = 30.0

#: Deadline of each cancel sent while a browser or context closes, in seconds.
STOP_TIMEOUT = 2.0

_ANY = object()  # every browser context, for Downloads.stop


class DownloadError(Exception):
    """A download was canceled, interrupted, or its browser closed first."""


class Download:
    """One file Chrome is downloading (or has downloaded).

    The file is named by :attr:`guid` in its browser context's downloads
    folder; :meth:`save_as` copies it under a name of your choice.
    """

    def __init__(
        self, downloads: Downloads, params: dict, context_id: str | None, folder: Path
    ) -> None:
        self._downloads = downloads
        self._context_id = context_id
        self._folder = folder
        self.url: str = params.get("url", "")
        self.suggested_filename: str = params.get("suggestedFilename", "")
        self.guid: str = params["guid"]
        self.frame_id: str = params.get("frameId", "")
        self.state = "inProgress"  # then "completed" or "canceled"
        self.received_bytes = 0
        self.total_bytes = 0
        self._file: Path | None = None
        self._error: DownloadError | None = None
        self._stop_error: DownloadError | None = None  # why its owner canceled it
        self._done = asyncio.Event()

    @property
    def context_id(self) -> str | None:
        """The browser context it belongs to (``None``: the default one)."""
        return self._context_id

    def __repr__(self) -> str:
        return f"<Download {self.suggested_filename!r} {self.state} ({self.guid})>"

    def _progress(self, params: dict) -> None:
        self.received_bytes = int(params.get("receivedBytes", self.received_bytes))
        self.total_bytes = int(params.get("totalBytes", self.total_bytes))
        state = params.get("state", self.state)
        if state == "completed":
            self._file = Path(params.get("filePath") or self._folder / self.guid)
            self._finish(state)
        elif state == "canceled":
            error = self._stop_error or DownloadError(f"Download of {self.url} was canceled")
            self._finish(state, error)

    def _finish(self, state: str, error: DownloadError | None = None) -> None:
        if self._done.is_set():
            return
        self.state, self._error = state, error
        self._done.set()
        self._downloads._active.pop(self.guid, None)

    async def _wait(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._done.wait(), timeout)
        except asyncio.TimeoutError:  # not the builtin TimeoutError on Python 3.10
            raise TimeoutError(
                f"Download of {self.url} did not finish within {timeout:g}s"
            ) from None

    async def path(self, timeout: float = DEFAULT_TIMEOUT) -> Path:
        """Wait for the download to complete and return where the file is.

        Raises :class:`DownloadError` when it was canceled or the browser
        closed first, :class:`TimeoutError` after *timeout* seconds.
        """
        await self._wait(timeout)
        if self._error is not None:
            raise DownloadError(*self._error.args)
        assert self._file is not None
        return self._file

    async def save_as(self, path: str | Path, timeout: float = DEFAULT_TIMEOUT) -> Path:
        """Wait for the download to complete, copy it to *path* and return it.

        Missing parent folders are created. The copy runs off the event loop.
        """
        source = await self.path(timeout)
        target = Path(path)
        await asyncio.to_thread(_copy, source, target)
        return target

    async def cancel(self, timeout: float = 10.0) -> None:
        """Cancel the download (no-op once it finished) and wait until Chrome
        reports it canceled; Chrome deletes the partial file."""
        if self._done.is_set():
            return
        params: dict[str, Any] = {"guid": self.guid}
        if self._context_id is not None:
            params["browserContextId"] = self._context_id
        await self._downloads._session.send("Browser.cancelDownload", params, timeout=timeout)
        await self._wait(timeout)

    async def _stop(self, error: DownloadError) -> None:
        """Cancel on behalf of a closing browser or context: Chrome deletes the
        partial file; whatever happens, waits fail with *error*."""
        self._stop_error = error
        try:
            await self.cancel(STOP_TIMEOUT)
        except Exception:  # noqa: BLE001 - Chrome may be gone already
            pass
        finally:
            self._finish("canceled", error)


def _copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


class DownloadWaiter:
    """Waits for the next download a frame filter accepts.

    ``async with waiter as info: <start the download>`` then
    ``download = await info.value``. Leaving the block waits for the download
    to begin (at most *timeout* seconds since entering it); an error raised
    inside the block discards the waiter instead.
    """

    def __init__(
        self,
        downloads: Downloads,
        accepts: Callable[[str], bool] | None,
        context_id: str | None,
        timeout: float,
    ) -> None:
        self._downloads = downloads
        self._accepts = accepts
        self.context_id = context_id
        self._timeout = timeout
        self._deadline = 0.0
        self._future: asyncio.Future[Download] = asyncio.get_running_loop().create_future()

    def accepts(self, frame_id: str) -> bool:
        """Whether this waiter takes a download of *frame_id*; a filter that
        raises fails this waiter alone."""
        if self._future.done():
            return False
        try:
            return self._accepts is None or bool(self._accepts(frame_id))
        except Exception as exc:  # noqa: BLE001 - handed to the waiter
            self._fail(exc)
            return False

    async def __aenter__(self) -> DownloadWaiter:
        self._deadline = asyncio.get_running_loop().time() + self._timeout
        self._downloads._waiters.append(self)
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None:
            self._fail(DownloadError("The block raised before a download began"))
            self._discard()
            return
        try:
            await self.value
        finally:
            self._discard()

    @property
    def value(self) -> Awaitable[Download]:
        """Awaitable: the :class:`Download`, once it has begun."""
        return self._result()

    async def _result(self) -> Download:
        if self._future.done():
            return self._future.result()
        remaining = max(0.0, self._deadline - asyncio.get_running_loop().time())
        try:
            return await asyncio.wait_for(asyncio.shield(self._future), remaining)
        except asyncio.TimeoutError:
            raise TimeoutError(f"No download began within {self._timeout:g}s") from None

    def _resolve(self, download: Download) -> None:
        if not self._future.done():
            self._future.set_result(download)

    def _fail(self, error: Exception) -> None:
        if not self._future.done():
            self._future.set_exception(error)
            self._future.exception()  # retrieved: never logged as unhandled

    def _discard(self) -> None:
        if self in self._downloads._waiters:
            self._downloads._waiters.remove(self)


class Downloads:
    """The downloads of one browser: a folder per browser context, the
    downloads in progress and the waiters for the next ones."""

    def __init__(self, locate: Callable[[str], str | None] | None = None) -> None:
        # frame id -> its browser context ("" for the default one), None if unknown
        self._locate = locate
        self._session: Any = None
        self._folders: dict[str | None, tuple[Path, bool]] = {}  # context -> (folder, owned)
        self._active: dict[str, Download] = {}
        self._waiters: list[DownloadWaiter] = []

    def folder(self, context_id: str | None = None) -> Path:
        """Where the downloads of *context_id* (``None``: the default context) go."""
        return self._folders[context_id][0]

    async def start(
        self, session: Any, folder: str | Path, owned: bool, reader: asyncio.Task | None = None
    ) -> None:
        """Save the default context's downloads in *folder* and listen for them.

        *owned* folders are temporary: their owner removes them. When the
        *reader* of the CDP pipe ends (Chrome closed or crashed), every wait
        fails at once.
        """
        self._session = session
        session.on("Browser.downloadWillBegin", self._on_will_begin)
        session.on("Browser.downloadProgress", self._on_progress)
        if reader is not None:
            reader.add_done_callback(lambda _: self._lost())
        await self._allow(None, Path(folder), owned)

    async def add_context(self, context_id: str, folder: str | Path | None = None) -> Path:
        """Give *context_id* its own folder: *folder*, kept; or by default a
        subfolder of the browser's, temporary when the browser's is."""
        if folder is not None:
            return await self._allow(context_id, Path(folder), False)
        parent, owned = self._folders[None]
        return await self._allow(context_id, parent / context_id, owned)

    async def remove_context(self, context_id: str) -> None:
        """Forget *context_id*, removing its folder when temporary."""
        folder, owned = self._folders.pop(context_id, (None, False))
        if owned and folder is not None:
            await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)

    async def _allow(self, context_id: str | None, folder: Path, owned: bool) -> Path:
        folder = Path(os.path.abspath(folder))  # Chrome and path() must agree
        await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
        self._folders[context_id] = (folder, owned)
        params: dict[str, Any] = {
            "behavior": "allowAndName",
            "downloadPath": str(folder),
            "eventsEnabled": True,
        }
        if context_id is not None:
            params["browserContextId"] = context_id
        await self._session.send("Browser.setDownloadBehavior", params)
        return folder

    def expect(
        self,
        accepts: Callable[[str], bool] | None = None,
        *,
        context_id: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> DownloadWaiter:
        """A waiter for the next download started by a frame *accepts* takes
        (any frame when ``None``). *context_id* is the browser context of
        those frames, used when the frame is not a known tab."""
        return DownloadWaiter(self, accepts, context_id, timeout)

    def expect_frames(
        self, frames: TabFrames, *, timeout: float = DEFAULT_TIMEOUT
    ) -> DownloadWaiter:
        """A waiter for the next download of one tab: started by one of its *frames*,
        saved in the folder of the browser context of its main frame."""
        located = self._locate(frames.main) if self._locate is not None else None
        return self.expect(frames.__contains__, context_id=located or None, timeout=timeout)

    def _on_will_begin(self, params: dict) -> None:
        frame_id = params.get("frameId", "")
        waiter = next((w for w in self._waiters if w.accepts(frame_id)), None)
        if waiter is None:
            return  # nobody waits for it: Chrome still saves it in the folder
        located = self._locate(frame_id) if self._locate is not None else None
        context_id = waiter.context_id if located is None else (located or None)
        folder, _ = self._folders.get(context_id) or self._folders[None]
        download = Download(self, params, context_id, folder)
        self._active[download.guid] = download
        waiter._resolve(download)

    def _on_progress(self, params: dict) -> None:
        download = self._active.get(params.get("guid", ""))
        if download is not None:
            download._progress(params)

    async def stop(self, reason: str, context_id: Any = _ANY) -> None:
        """Cancel the unfinished downloads of *context_id* (default: all) and
        fail them and its waiters with ``DownloadError(reason)``.

        Run before the context or browser goes away, so Chrome deletes the
        partial files; each cancel is bounded by :data:`STOP_TIMEOUT`.
        """
        for waiter in list(self._waiters):
            if context_id is _ANY or waiter.context_id == context_id:
                waiter._fail(DownloadError(reason))
                waiter._discard()
        downloads = [
            d for d in self._active.values() if context_id is _ANY or d.context_id == context_id
        ]
        await asyncio.gather(*(d._stop(DownloadError(reason)) for d in downloads))

    def _lost(self) -> None:
        """The pipe to Chrome is gone: nothing will ever be reported again."""
        reason = "Chrome closed or crashed"
        for waiter in list(self._waiters):
            waiter._fail(DownloadError(reason))
        for download in list(self._active.values()):
            download._finish("canceled", DownloadError(reason))
        self._waiters.clear()


class TabFrames:
    """The frame ids of one tab's page, kept from its ``Page`` frame events, so a
    download started by one of its same-process iframes reaches the tab's waiter.

    An iframe joins on ``Page.frameAttached``: one that never commits a document
    (its src is a download, or a page of another site, an OOPIF from the start)
    sends no ``Page.frameNavigated`` to the tab's session. Iframes nested inside
    a cross-site iframe are reported to that iframe's own session only, and are
    not covered. Frame ids are unique across the browser: a kept id never names
    another tab's frame. A removed iframe leaves the set; a main-frame
    navigation drops the old document's frames.
    """

    def __init__(self, session: Any, main_frame_id: str) -> None:
        self._main = main_frame_id
        self._ids = {main_frame_id}
        session.on("Page.frameAttached", self._on_attached)
        session.on("Page.frameNavigated", self._on_navigated)
        session.on("Page.frameDetached", self._on_detached)

    @property
    def main(self) -> str:
        """The id of the tab's main frame."""
        return self._main

    def __contains__(self, frame_id: object) -> bool:
        return bool(frame_id) and frame_id in self._ids

    def _on_navigated(self, params: dict) -> None:
        frame = params.get("frame", {})
        if not frame.get("parentId"):
            self._main = frame.get("id") or self._main
            self._ids = {self._main}
        elif frame.get("id"):
            self._ids.add(frame["id"])

    def _on_attached(self, params: dict) -> None:
        if params.get("frameId"):
            self._ids.add(params["frameId"])

    def _on_detached(self, params: dict) -> None:
        # "swap": the frame moves to another process under the same id, still ours
        if params.get("reason") != "swap" and params.get("frameId") != self._main:
            self._ids.discard(params.get("frameId", ""))
