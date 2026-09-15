"""Tests for request duration timing calculation."""

from tellurium.capture.manager import CaptureManager


def test_duration_calculated_from_elapsed_time():
    """Duration should be (finished_timestamp - request_timestamp) * 1000 ms."""
    mgr = CaptureManager(None)

    # Simulate request at t=1000.0
    mgr._on_request(
        {
            "requestId": "r1",
            "timestamp": 1000.0,
            "request": {"url": "https://api.example.com/data", "method": "GET", "headers": {}},
        }
    )

    # Simulate response (doesn't affect duration)
    mgr._on_response(
        {
            "requestId": "r1",
            "response": {
                "status": 200,
                "headers": {},
                "mimeType": "application/json",
                "encodedDataLength": 500,
            },
        }
    )

    # Simulate finished at t=1000.220 (220ms elapsed)
    mgr._on_finished(
        {
            "requestId": "r1",
            "timestamp": 1000.220,
        }
    )

    req = mgr._by_id["r1"]
    assert req._complete is True
    assert 219 <= req.duration <= 221  # ~220ms with float tolerance


def test_duration_zero_when_timestamps_missing():
    """Gracefully handle missing timestamps (older Chrome, redirects)."""
    mgr = CaptureManager(None)

    # Request without timestamp
    mgr._on_request(
        {
            "requestId": "r2",
            "request": {"url": "https://x.com", "method": "GET", "headers": {}},
        }
    )

    # Finished without timestamp
    mgr._on_finished({"requestId": "r2"})

    req = mgr._by_id["r2"]
    assert req.duration == 0
