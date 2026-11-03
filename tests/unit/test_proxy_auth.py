"""ProxyAuth: Chrome's answer to the forwarder's 407, against a fake CDP session."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from tellurium.browser.proxy_auth import ProxyAuth

pytestmark = pytest.mark.asyncio

SECRET = "s" * 43
FORWARDER = SimpleNamespace(port=41234, credentials=("tellurium", SECRET))


class FakeSession:
    """Records every command; *hang* makes the named methods never answer."""

    def __init__(self, hang: tuple[str, ...] = ()) -> None:
        self.sent: list[tuple[str, dict, float | None]] = []
        self.handlers: dict[str, list] = {}
        self.hang = hang
        self.cancelled = 0

    async def send(self, method: str, params: dict | None = None, timeout: float | None = None):
        self.sent.append((method, params or {}, timeout))
        if method in self.hang:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled += 1
                raise
        return {}

    def on(self, event: str, handler) -> None:
        self.handlers.setdefault(event, []).append(handler)

    def off(self, event: str, handler) -> None:
        self.handlers.get(event, []).remove(handler)

    def emit(self, event: str, params: dict) -> None:
        for handler in list(self.handlers.get(event, [])):
            handler(params)

    def answers(self) -> list[tuple[str, dict]]:
        return [(m, p) for m, p, _ in self.sent if m != "Fetch.enable"]


def _challenge(request_id: str, source: str = "Proxy", origin: str | None = None) -> dict:
    return {
        "requestId": request_id,
        "request": {"url": "http://site.test/", "method": "GET", "headers": {}},
        "authChallenge": {
            "source": source,
            "origin": origin or f"http://127.0.0.1:{FORWARDER.port}",
            "scheme": "basic",
            "realm": "tellurium",
        },
    }


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def _started(session: FakeSession) -> ProxyAuth:
    auth = ProxyAuth(session, FORWARDER)
    await auth.start()
    return auth


async def test_start_enables_fetch_with_auth_requests_for_every_url():
    session = FakeSession()
    await _started(session)
    ((method, params, timeout),) = session.sent
    assert method == "Fetch.enable"
    assert params == {"handleAuthRequests": True, "patterns": [{"urlPattern": "*"}]}
    assert timeout is not None and timeout > 0
    assert session.handlers["Fetch.requestPaused"] and session.handlers["Fetch.authRequired"]


async def test_every_paused_request_is_continued_at_once():
    session = FakeSession()
    await _started(session)
    for i in range(3):
        session.emit("Fetch.requestPaused", {"requestId": f"r{i}", "request": {}})
    await _settle()
    assert session.answers() == [
        ("Fetch.continueRequest", {"requestId": f"r{i}"}) for i in range(3)
    ]
    assert all(t is not None for _, _, t in session.sent)


async def test_the_forwarder_challenge_gets_the_secret_once_then_cancel():
    session = FakeSession()
    await _started(session)
    session.emit("Fetch.authRequired", _challenge("r1"))
    session.emit("Fetch.authRequired", _challenge("r1"))
    await _settle()
    provide = {"response": "ProvideCredentials", "username": "tellurium", "password": SECRET}
    assert session.answers() == [
        ("Fetch.continueWithAuth", {"requestId": "r1", "authChallengeResponse": provide}),
        (
            "Fetch.continueWithAuth",
            {"requestId": "r1", "authChallengeResponse": {"response": "CancelAuth"}},
        ),
    ]


@pytest.mark.parametrize(
    "challenge",
    [
        _challenge("r1", source="Server"),  # a site's 401
        _challenge("r1", origin="http://127.0.0.1:1"),  # another proxy
        _challenge("r1", origin="http://proxy.test:41234"),
        _challenge("r1", origin="not a url"),
    ],
    ids=["server", "other-port", "other-host", "garbage"],
)
async def test_any_other_challenge_gets_the_default_answer(challenge):
    session = FakeSession()
    await _started(session)
    session.emit("Fetch.authRequired", challenge)
    await _settle()
    assert session.answers() == [
        (
            "Fetch.continueWithAuth",
            {"requestId": "r1", "authChallengeResponse": {"response": "Default"}},
        )
    ]


async def test_stop_cancels_answers_in_flight_and_ignores_later_events():
    session = FakeSession(hang=("Fetch.continueRequest", "Fetch.continueWithAuth"))
    auth = await _started(session)
    session.emit("Fetch.requestPaused", {"requestId": "r1"})
    session.emit("Fetch.authRequired", _challenge("r2"))
    await _settle()
    await asyncio.wait_for(auth.stop(), 1.0)
    assert session.cancelled == 2
    assert not session.handlers["Fetch.requestPaused"]
    assert not session.handlers["Fetch.authRequired"]
    sent = len(session.sent)
    await auth.stop()  # idempotent
    assert len(session.sent) == sent


async def test_a_failed_answer_is_logged_without_the_secret(caplog):
    caplog.set_level(logging.DEBUG, logger="tellurium")

    class Failing(FakeSession):
        async def send(self, method, params=None, timeout=None):
            await super().send(method, params, timeout)
            if method != "Fetch.enable":
                raise ConnectionError("Browser pipe closed")
            return {}

    session = Failing()
    auth = await _started(session)
    session.emit("Fetch.authRequired", _challenge("r1"))
    await _settle()
    await auth.stop()
    assert "continueWithAuth" in caplog.text
    assert SECRET not in caplog.text + repr(auth)


async def test_start_fails_and_unwires_when_fetch_enable_fails():
    class Refusing(FakeSession):
        async def send(self, method, params=None, timeout=None):
            raise TimeoutError(f"{method} got no reply within 10s")

    session = Refusing()
    with pytest.raises(TimeoutError):
        await ProxyAuth(session, FORWARDER).start()
    assert not any(session.handlers.values())


async def test_answered_requests_are_remembered_within_a_bound():
    session = FakeSession()
    auth = await _started(session)
    for i in range(5000):
        session.emit("Fetch.authRequired", _challenge(f"r{i}"))
    await _settle()
    assert len(auth._answered) <= 4096
    await auth.stop()
