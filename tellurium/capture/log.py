"""Live network capture logger."""
from __future__ import annotations
import fnmatch
import sys
from urllib.parse import urlparse


class CaptureLogger:
    def __init__(self, filter_pattern: str | None = None):
        self._filter = filter_pattern

    def log_response(self, req) -> None:
        if not self._should_log(req):
            return
        type_label = self._format_type(req.content_type or "")
        size_label = self._format_size(req.size)
        parsed = urlparse(req.url)
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
        line = (
            f"[tellurium] {req.method:<6} {path:<40} "
            f"-> {req.status}  [{type_label} {size_label}]"
        )
        print(line, file=sys.stderr)

    def _should_log(self, req) -> bool:
        if self._filter is None:
            return True
        if self._filter == "json":
            return "json" in (req.content_type or "").lower()
        return fnmatch.fnmatch(req.url, self._filter)

    def _format_type(self, mime: str) -> str:
        for prefix, label in {
            "application/json": "JSON", "text/html": "HTML",
            "application/javascript": "JS", "text/css": "CSS",
            "image/": "Image", "font/": "Font",
        }.items():
            if mime.startswith(prefix):
                return label
        return mime.split("/")[-1].upper()[:8] if mime else "?"

    @staticmethod
    def _format_size(bytes_: int) -> str:
        if bytes_ < 1024:
            return f"{bytes_}B"
        elif bytes_ < 1024 * 1024:
            return f"{bytes_ / 1024:.1f}KB"
        return f"{bytes_ / 1024 / 1024:.1f}MB"
