import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

from tellurium.capture.log import CaptureLogger
from tellurium.capture.manager import CaptureManager
from tellurium.capture.recorder import RecordingSession
from tellurium.capture.request import CapturedRequest

# --- CapturedRequest tests ---


def test_request_match_url():
    req = CapturedRequest(url="https://example.com/api/feed?page=1", method="GET")
    assert req._match_url("*/api/*")
    assert req._match_url("*feed*")
    assert not req._match_url("*/other/*")


def test_request_defaults():
    req = CapturedRequest(url="https://x.com", method="POST")
    assert req.status is None
    assert req.headers == {}
    assert req.size == 0
    assert req._complete is False


# --- CaptureManager search tests ---


def test_search_by_url():
    mgr = CaptureManager(None)
    mgr._requests = [
        CapturedRequest(url="https://example.com/api/feed", method="GET"),
        CapturedRequest(url="https://example.com/assets/main.js", method="GET"),
    ]
    results = mgr.search(url="*/api/*")
    assert len(results) == 1
    assert "feed" in results[0].url


def test_search_by_method():
    mgr = CaptureManager(None)
    mgr._requests = [
        CapturedRequest(url="https://a.com", method="GET"),
        CapturedRequest(url="https://b.com", method="POST"),
    ]
    results = mgr.search(method="POST")
    assert len(results) == 1
    assert results[0].method == "POST"


def test_search_by_status():
    mgr = CaptureManager(None)
    mgr._requests = [
        CapturedRequest(url="https://a.com", method="GET", status=200),
        CapturedRequest(url="https://b.com", method="GET", status=404),
        CapturedRequest(url="https://c.com", method="GET", status=500),
    ]
    assert len(mgr.search(status=200)) == 1
    assert len(mgr.search(status=range(400, 500))) == 1


def test_search_by_content_type():
    mgr = CaptureManager(None)
    mgr._requests = [
        CapturedRequest(url="https://a.com", method="GET", content_type="application/json"),
        CapturedRequest(url="https://b.com", method="GET", content_type="text/html"),
    ]
    results = mgr.search(content_type="json")
    assert len(results) == 1


def test_search_by_header():
    mgr = CaptureManager(None)
    mgr._requests = [
        CapturedRequest(
            url="https://a.com", method="GET", request_headers={"Authorization": "Bearer x"}
        ),
        CapturedRequest(url="https://b.com", method="GET", request_headers={"Accept": "text/html"}),
    ]
    results = mgr.search(header="Authorization")
    assert len(results) == 1


def test_search_combined_filters():
    mgr = CaptureManager(None)
    mgr._requests = [
        CapturedRequest(
            url="https://a.com/api/data", method="GET", status=200, content_type="application/json"
        ),
        CapturedRequest(
            url="https://a.com/api/data", method="POST", status=200, content_type="application/json"
        ),
        CapturedRequest(
            url="https://a.com/page", method="GET", status=200, content_type="text/html"
        ),
    ]
    results = mgr.search(url="*/api/*", method="GET", content_type="json")
    assert len(results) == 1


# --- CaptureLogger tests ---


def test_logger_format_size():
    assert CaptureLogger._format_size(500) == "500B"
    assert CaptureLogger._format_size(1536) == "1.5KB"
    assert CaptureLogger._format_size(2 * 1024 * 1024) == "2.0MB"


def test_logger_should_log_no_filter():
    logger = CaptureLogger(None)
    req = CapturedRequest(url="https://a.com", method="GET", content_type="text/html")
    assert logger._should_log(req) is True


def test_logger_should_log_json_filter():
    logger = CaptureLogger("json")
    req_json = CapturedRequest(url="https://a.com", method="GET", content_type="application/json")
    req_html = CapturedRequest(url="https://a.com", method="GET", content_type="text/html")
    assert logger._should_log(req_json) is True
    assert logger._should_log(req_html) is False


def test_logger_should_log_url_filter():
    logger = CaptureLogger("*/api/*")
    req_api = CapturedRequest(url="https://a.com/api/data", method="GET")
    req_other = CapturedRequest(url="https://a.com/page", method="GET")
    assert logger._should_log(req_api) is True
    assert logger._should_log(req_other) is False


# --- RecordingSession tests ---


def test_recording_session_save(tmp_path):
    session = RecordingSession(
        created_at="2026-04-14T14:00:00Z",
        duration_seconds=5.0,
        requests=[{"method": "GET", "url": "https://a.com", "status": 200}],
        cookies_at_export=[{"name": "sid", "value": "x", "domain": ".a.com"}],
    )
    path = str(tmp_path / "recording.json")
    session.save(path)
    with open(path) as f:
        data = json.load(f)
    assert data["tellurium_version"] == "0.1.0"
    assert len(data["requests"]) == 1
    assert data["requests"][0]["status"] == 200
    assert len(data["cookies_at_export"]) == 1
    assert data["cookies_at_export"][0]["name"] == "sid"


# --- CaptureManager event handlers ---


def test_on_request_creates_captured_request():
    mgr = CaptureManager(None)
    mgr._on_request(
        {
            "requestId": "r1",
            "request": {
                "url": "https://a.com/api",
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
            },
        }
    )
    assert len(mgr._requests) == 1
    assert mgr._requests[0].url == "https://a.com/api"
    assert mgr._requests[0].method == "POST"
    assert "r1" in mgr._by_id


def test_on_response_updates_request():
    mgr = CaptureManager(None)
    mgr._on_request(
        {"requestId": "r1", "request": {"url": "https://a.com", "method": "GET", "headers": {}}}
    )
    mgr._on_response(
        {
            "requestId": "r1",
            "response": {
                "status": 200,
                "headers": {"X-Custom": "val"},
                "mimeType": "application/json",
                "encodedDataLength": 1024,
            },
        }
    )
    req = mgr._by_id["r1"]
    assert req.status == 200
    assert req.content_type == "application/json"
    assert req.size == 1024


def test_on_finished_marks_complete():
    mgr = CaptureManager(None)
    mgr._on_request(
        {"requestId": "r1", "request": {"url": "https://a.com", "method": "GET", "headers": {}}}
    )
    mgr._on_response(
        {
            "requestId": "r1",
            "response": {"status": 200, "headers": {}, "mimeType": "", "encodedDataLength": 0},
        }
    )
    mgr._on_finished({"requestId": "r1"})
    assert mgr._by_id["r1"]._complete is True


# --- Cookies export tests ---


def test_recording_session_includes_cookies():
    """Recorder.export() should fetch and include cookies."""
    from tellurium.capture.recorder import Recorder

    session_mock = MagicMock()
    session_mock.send = AsyncMock(
        return_value={
            "cookies": [
                {"name": "session_id", "value": "abc123", "domain": ".example.com"},
                {"name": "token", "value": "xyz", "domain": "api.example.com"},
            ]
        }
    )

    mgr = CaptureManager(session_mock)
    mgr._requests = [
        CapturedRequest(url="https://example.com/api", method="GET", status=200),
    ]

    recorder = Recorder(mgr, "*")

    session = asyncio.run(recorder.export())

    assert hasattr(session, "cookies_at_export")
    assert len(session.cookies_at_export) == 2
    assert session.cookies_at_export[0]["name"] == "session_id"


def test_recording_export_graceful_when_session_none():
    """Recorder.export() returns empty cookies when session is None."""
    from tellurium.capture.recorder import Recorder

    mgr = CaptureManager(None)  # No session
    recorder = Recorder(mgr, "*")

    session = asyncio.run(recorder.export())

    assert session.cookies_at_export == []
