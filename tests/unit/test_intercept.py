"""Tests for Fetch-based request interception."""

import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock

from tellurium.capture.intercept import InterceptedRequest, InterceptStream


def test_intercepted_request_continue():
    """continue_() sends Fetch.continueRequest with original params."""
    session = MagicMock()
    session.send = AsyncMock()

    req = InterceptedRequest(
        request_id="fetch_1",
        url="https://api.example.com/data",
        method="GET",
        headers={"Accept": "application/json"},
        session=session,
    )

    asyncio.run(req.continue_())

    session.send.assert_called_once()
    method, params = session.send.call_args[0]
    assert method == "Fetch.continueRequest"
    assert params["requestId"] == "fetch_1"


def test_intercepted_request_continue_with_modified_headers():
    """continue_(headers=...) sends modified headers."""
    session = MagicMock()
    session.send = AsyncMock()

    req = InterceptedRequest(
        request_id="fetch_2",
        url="https://api.example.com/data",
        method="GET",
        headers={},
        session=session,
    )

    asyncio.run(req.continue_(headers={"X-Custom": "value", "Authorization": "Bearer tok"}))

    method, params = session.send.call_args[0]
    assert method == "Fetch.continueRequest"
    assert params["headers"] == [
        {"name": "X-Custom", "value": "value"},
        {"name": "Authorization", "value": "Bearer tok"},
    ]


def test_intercepted_request_abort():
    """abort() sends Fetch.failRequest with Aborted reason."""
    session = MagicMock()
    session.send = AsyncMock()

    req = InterceptedRequest(
        request_id="fetch_3",
        url="https://blocked.com/tracker",
        method="GET",
        headers={},
        session=session,
    )

    asyncio.run(req.abort())

    method, params = session.send.call_args[0]
    assert method == "Fetch.failRequest"
    assert params["requestId"] == "fetch_3"
    assert params["errorReason"] == "Aborted"


def test_intercepted_request_respond():
    """respond() sends Fetch.fulfillRequest with mock response."""
    session = MagicMock()
    session.send = AsyncMock()

    req = InterceptedRequest(
        request_id="fetch_4",
        url="https://api.example.com/mock",
        method="GET",
        headers={},
        session=session,
    )

    asyncio.run(
        req.respond(status=200, body='{"mock": true}', headers={"Content-Type": "application/json"})
    )

    method, params = session.send.call_args[0]
    assert method == "Fetch.fulfillRequest"
    assert params["requestId"] == "fetch_4"
    assert params["responseCode"] == 200
    # Body is base64 encoded
    assert base64.b64decode(params["body"]).decode() == '{"mock": true}'


def test_intercept_stream_lifecycle():
    """InterceptStream enables Fetch on start, disables on stop."""
    session = MagicMock()
    session.send = AsyncMock()
    session.on = MagicMock()
    session.off = MagicMock()

    stream = InterceptStream(session, url_pattern="*/api/*")

    asyncio.run(stream.start())

    # Fetch.enable called with URL pattern
    enable_call = session.send.call_args_list[0]
    method, params = enable_call[0]
    assert method == "Fetch.enable"
    assert params["patterns"][0]["urlPattern"] == "*/api/*"

    # Handler registered
    session.on.assert_called_once()
    event_name = session.on.call_args[0][0]
    assert event_name == "Fetch.requestPaused"

    asyncio.run(stream.stop())

    # Fetch.disable called
    disable_call = session.send.call_args_list[1]
    assert disable_call[0][0] == "Fetch.disable"

    # Handler unregistered
    session.off.assert_called_once()


def test_intercept_stream_yields_paused_requests():
    """_on_paused() creates InterceptedRequest that can be yielded via async iteration."""
    session = MagicMock()
    session.send = AsyncMock()
    session.on = MagicMock()
    session.off = MagicMock()

    stream = InterceptStream(session, url_pattern="*")

    async def run():
        await stream.start()

        # Simulate Fetch.requestPaused event
        stream._on_paused(
            {
                "requestId": "paused_1",
                "request": {
                    "url": "https://example.com/api",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                },
            }
        )

        # Should be able to get the request from the queue
        req = await asyncio.wait_for(stream._queue.get(), timeout=1.0)

        assert req.request_id == "paused_1"
        assert req.url == "https://example.com/api"
        assert req.method == "POST"

        await stream.stop()

    asyncio.run(run())


def test_tab_intercept_returns_intercept_stream():
    """Tab.intercept() returns an InterceptStream usable as async context manager."""
    from tellurium.browser.tab import Tab

    tab = Tab.__new__(Tab)
    tab._session = MagicMock()
    tab._session.send = AsyncMock()
    tab._session.on = MagicMock()
    tab._session.off = MagicMock()

    stream = tab.intercept("*/api/*")

    # Should return InterceptStream
    assert isinstance(stream, InterceptStream)
    # Should have async context manager methods
    assert hasattr(stream, "__aenter__")
    assert hasattr(stream, "__aexit__")
