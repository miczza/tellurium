"""TabFrames and Downloads.expect_frames without Chrome."""

from __future__ import annotations

from tellurium.browser.download import Downloads, TabFrames


class _Session:
    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}

    def on(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, params: dict) -> None:
        for handler in self.handlers.get(event, []):
            handler(params)


def _navigated(frame_id: str, parent: str | None = None) -> dict:
    frame = {"id": frame_id} | ({"parentId": parent} if parent else {})
    return {"frame": frame}


def test_frames_follow_navigations_and_detaches():
    session = _Session()
    frames = TabFrames(session, "MAIN")
    session.emit("Page.frameNavigated", _navigated("A", "MAIN"))
    session.emit("Page.frameNavigated", _navigated("B", "MAIN"))
    session.emit("Page.frameAttached", {"frameId": "OOPIF", "parentFrameId": "MAIN"})
    assert "A" in frames and "B" in frames and "OOPIF" in frames and "" not in frames
    session.emit("Page.frameDetached", {"frameId": "A", "reason": "remove"})
    session.emit("Page.frameDetached", {"frameId": "B", "reason": "swap"})
    session.emit("Page.frameDetached", {"frameId": "MAIN", "reason": "remove"})
    assert "A" not in frames and "B" in frames and "MAIN" in frames
    session.emit("Page.frameNavigated", _navigated("MAIN"))
    assert "B" not in frames and frames.main == "MAIN"


async def test_expect_frames_takes_the_context_of_the_main_frame():
    contexts = {"MAIN": "", "CTXMAIN": "ctx"}
    downloads = Downloads(contexts.get)
    session, other_session = _Session(), _Session()
    default, other = TabFrames(session, "MAIN"), TabFrames(other_session, "CTXMAIN")
    other_session.emit("Page.frameNavigated", _navigated("CHILD", "CTXMAIN"))
    assert downloads.expect_frames(default).context_id is None
    waiter = downloads.expect_frames(other, timeout=5)
    assert waiter.context_id == "ctx"
    assert waiter.accepts("CHILD") and waiter.accepts("CTXMAIN") and not waiter.accepts("MAIN")
