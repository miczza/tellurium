"""The relay's own browser session on a fake pipe: hidden from the client both ways."""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("websockets")

from tellurium.browser.proxy_auth import ProxyAuth  # noqa: E402
from tellurium.multiplexer.own_session import OwnSession  # noqa: E402
from tellurium.multiplexer.relay import CommandError, Relay  # noqa: E402
from tests.unit.test_multiplexer_relay import FakePipe, FakeSocket, _until  # noqa: E402

OWN = "OWN-SESSION"


async def _attached(pipe: FakePipe, relay: Relay) -> OwnSession:
    attaching = asyncio.ensure_future(OwnSession.attach(relay, 2))
    await _until(lambda: pipe.sent)
    command = pipe.sent[-1]
    assert command["method"] == "Target.attachToBrowserTarget" and "sessionId" not in command
    pipe.incoming.put_nowait({"id": command["id"], "result": {"sessionId": OWN}})
    return await attaching


async def _relay_with_client() -> tuple[FakePipe, FakeSocket, Relay, asyncio.Future]:
    pipe, ws = FakePipe(), FakeSocket()
    relay = Relay(pipe)
    relay.start()
    serving = asyncio.ensure_future(relay.serve(ws))
    await _until(lambda: relay._client is not None)
    return pipe, ws, relay, serving


async def _done(ws: FakeSocket, relay: Relay, serving: asyncio.Future) -> None:
    ws.inbox.put_nowait(None)
    await serving
    await relay.close()


async def test_commands_and_events_of_the_own_session_never_reach_the_client():
    pipe, ws, relay, serving = await _relay_with_client()
    session = await _attached(pipe, relay)
    seen: list[dict] = []
    session.on("Fetch.requestPaused", seen.append)

    sending = asyncio.ensure_future(session.send("Fetch.enable", {"a": 1}, timeout=2))
    await _until(lambda: len(pipe.sent) == 2)
    command = pipe.sent[-1]
    assert command["sessionId"] == OWN and command["params"] == {"a": 1}
    pipe.incoming.put_nowait({"id": command["id"], "result": {"ok": 1}, "sessionId": OWN})
    assert await sending == {"ok": 1}

    paused = {"requestId": "r1", "request": {"url": "http://site.test/"}}
    pipe.incoming.put_nowait({"method": "Fetch.requestPaused", "params": paused, "sessionId": OWN})
    pipe.incoming.put_nowait({"method": "Other.event", "params": {}, "sessionId": OWN})
    for method in ("Target.attachedToTarget", "Target.detachedFromTarget"):
        pipe.incoming.put_nowait({"method": method, "params": {"sessionId": OWN}})
    pipe.incoming.put_nowait({"method": "Target.attachedToTarget", "params": {"sessionId": "C"}})
    await _until(lambda: ws.out)
    assert seen == [paused]
    assert ws.out == [{"method": "Target.attachedToTarget", "params": {"sessionId": "C"}}]

    session.off("Fetch.requestPaused", seen.append)
    pipe.incoming.put_nowait({"method": "Fetch.requestPaused", "params": paused, "sessionId": OWN})
    pipe.incoming.put_nowait({"method": "Last", "params": {}})
    await _until(lambda: len(ws.out) == 2)
    assert seen == [paused]
    await _done(ws, relay, serving)


async def test_an_error_reply_raises_and_a_silent_chrome_times_out():
    pipe, ws, relay, serving = await _relay_with_client()
    session = await _attached(pipe, relay)
    sending = asyncio.ensure_future(session.send("Fetch.enable", timeout=2))
    await _until(lambda: len(pipe.sent) == 2)
    error = {"code": -32602, "message": "Invalid parameters"}
    pipe.incoming.put_nowait({"id": pipe.sent[-1]["id"], "error": error, "sessionId": OWN})
    with pytest.raises(CommandError, match="Invalid parameters"):
        await sending
    with pytest.raises(TimeoutError):
        await session.send("Fetch.enable", timeout=0.05)
    assert ws.out == []
    await _done(ws, relay, serving)


async def test_the_client_cannot_drive_or_detach_the_own_session():
    pipe, ws, relay, serving = await _relay_with_client()
    await _attached(pipe, relay)
    sent = len(pipe.sent)
    ws.inbox.put_nowait(json.dumps({"id": 7, "method": "Fetch.disable", "sessionId": OWN}))
    detach = {"id": 8, "method": "Target.detachFromTarget", "params": {"sessionId": OWN}}
    ws.inbox.put_nowait(json.dumps(detach))
    ws.inbox.put_nowait(json.dumps({"id": 9, "method": "Browser.getVersion"}))
    await _until(lambda: len(ws.out) == 2 and len(pipe.sent) == sent + 1)
    assert [m["id"] for m in ws.out] == [7, 8]
    assert all(m["error"]["code"] == -32001 for m in ws.out)
    assert OWN not in json.dumps(ws.out)
    assert pipe.sent[-1]["method"] == "Browser.getVersion"
    # The relay does not count refused commands as waiting for Chrome.
    pipe.incoming.put_nowait({"id": pipe.sent[-1]["id"], "result": {}})
    await _until(lambda: len(ws.out) == 3)
    assert ws.out[-1] == {"id": 9, "result": {}} and relay._inflight == 0
    await _done(ws, relay, serving)


class _Forwarder:
    port = 4321
    credentials = ("tellurium", "the-secret")


async def test_proxy_auth_answers_on_the_own_session_and_the_client_sees_none_of_it():
    pipe, ws, relay, serving = await _relay_with_client()
    session = await _attached(pipe, relay)
    auth = ProxyAuth(session, _Forwarder())
    starting = asyncio.ensure_future(auth.start())
    await _until(lambda: len(pipe.sent) == 2)
    pipe.incoming.put_nowait({"id": pipe.sent[-1]["id"], "result": {}, "sessionId": OWN})
    await starting

    challenge = {"source": "Proxy", "origin": "http://127.0.0.1:4321", "scheme": "basic"}
    pipe.incoming.put_nowait(
        {"method": "Fetch.requestPaused", "params": {"requestId": "r1"}, "sessionId": OWN}
    )
    pipe.incoming.put_nowait(
        {
            "method": "Fetch.authRequired",
            "params": {"requestId": "r1", "authChallenge": challenge},
            "sessionId": OWN,
        }
    )
    await _until(lambda: len(pipe.sent) == 4)
    answers = pipe.sent[2:]
    assert [m["method"] for m in answers] == ["Fetch.continueRequest", "Fetch.continueWithAuth"]
    assert all(m["sessionId"] == OWN for m in answers)
    response = answers[1]["params"]["authChallengeResponse"]
    assert response["response"] == "ProvideCredentials" and response["password"] == "the-secret"
    for m in answers:
        pipe.incoming.put_nowait({"id": m["id"], "result": {}, "sessionId": OWN})
    await _until(lambda: not auth._tasks)
    await auth.stop()
    assert ws.out == []
    await _done(ws, relay, serving)
