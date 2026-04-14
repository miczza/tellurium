"""Recording mode — capture and export network sessions."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from tellurium.capture.manager import CaptureManager


class Recorder:
    def __init__(self, manager: CaptureManager, url_pattern: str = "*"):
        self._manager = manager
        self._url_pattern = url_pattern
        self._start_time = datetime.now(timezone.utc)

    def export(self) -> RecordingSession:
        requests = self._manager.search(url=self._url_pattern)
        return RecordingSession(
            created_at=self._start_time.isoformat(),
            duration_seconds=(datetime.now(timezone.utc) - self._start_time).total_seconds(),
            requests=[{
                "method": r.method,
                "url": r.url,
                "status": r.status,
                "request_headers": dict(r.request_headers),
                "response_headers": dict(r.headers),
                "size": r.size,
                "content_type": r.content_type,
            } for r in requests],
        )

    async def stop(self):
        await self._manager.stop()


class RecordingSession:
    def __init__(self, created_at: str, duration_seconds: float, requests: list[dict]):
        self.created_at = created_at
        self.duration_seconds = duration_seconds
        self.requests = requests

    def save(self, path: str) -> None:
        data = {
            "tellurium_version": "0.1.0",
            "created_at": self.created_at,
            "duration_seconds": self.duration_seconds,
            "requests": self.requests,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
