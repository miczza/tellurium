"""Captured network request with on-demand body retrieval."""
from __future__ import annotations
import fnmatch
import json as json_module
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CapturedRequest:
    url: str
    method: str
    status: int | None = None
    headers: dict = field(default_factory=dict)
    request_headers: dict = field(default_factory=dict)
    content_type: str | None = None
    size: int = 0
    duration: float = 0

    _request_id: str = ""
    _session: object = None
    _complete: bool = False
    _body_cache: str | None = None

    async def body(self) -> str:
        """Get response body (fetched on first call, cached)."""
        if self._body_cache is None:
            result = await self._session.send("Network.getResponseBody", {
                "requestId": self._request_id,
            })
            self._body_cache = result.get("body", "")
        return self._body_cache

    async def json(self) -> Any:
        """Get response body parsed as JSON."""
        return json_module.loads(await self.body())

    def _match_url(self, pattern: str) -> bool:
        return fnmatch.fnmatch(self.url, pattern)
