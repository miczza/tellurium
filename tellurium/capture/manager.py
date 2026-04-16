"""Capture manager — start/stop network monitoring, search, wait for requests."""
from __future__ import annotations
import asyncio
import fnmatch
from tellurium.capture.request import CapturedRequest
from tellurium.capture.log import CaptureLogger


class CaptureManager:
    def __init__(self, session):
        self._session = session
        self._requests: list[CapturedRequest] = []
        self._by_id: dict[str, CapturedRequest] = {}
        self._waiters: list[tuple[str, asyncio.Future]] = []
        self._active = False
        self._logger: CaptureLogger | None = None
        self._request_timestamps: dict[str, float] = {}

    async def start(self, log: bool = False, log_filter: str | None = None):
        await self._session.send("Network.enable", {})
        self._session.on("Network.requestWillBeSent", self._on_request)
        self._session.on("Network.responseReceived", self._on_response)
        self._session.on("Network.loadingFinished", self._on_finished)
        self._active = True
        if log:
            self._logger = CaptureLogger(log_filter)

    async def stop(self):
        if not self._active:
            return
        await self._session.send("Network.disable", {})
        self._session.off("Network.requestWillBeSent", self._on_request)
        self._session.off("Network.responseReceived", self._on_response)
        self._session.off("Network.loadingFinished", self._on_finished)
        self._active = False
        self._logger = None
        self._request_timestamps.clear()

    def search(self, **filters) -> list[CapturedRequest]:
        results = list(self._requests)
        if "url" in filters:
            pattern = filters["url"]
            results = [r for r in results if fnmatch.fnmatch(r.url, pattern)]
        if "method" in filters:
            method = filters["method"].upper()
            results = [r for r in results if r.method == method]
        if "status" in filters:
            s = filters["status"]
            if isinstance(s, range):
                results = [r for r in results if r.status in s]
            else:
                results = [r for r in results if r.status == s]
        if "content_type" in filters:
            ct = filters["content_type"].lower()
            results = [r for r in results if ct in (r.content_type or "").lower()]
        if "header" in filters:
            h = filters["header"].lower()
            results = [r for r in results if h in {k.lower() for k in r.request_headers}]
        return results

    async def search_body(self, body_contains: str, **filters) -> list[CapturedRequest]:
        candidates = self.search(**filters) if filters else list(self._requests)
        results = []
        for req in candidates:
            if req._complete:
                body = await req.body()
                if body_contains in body:
                    results.append(req)
        return results

    async def wait_for(self, url_pattern: str, timeout: float = 30) -> CapturedRequest:
        # Check already-captured requests
        for req in self._requests:
            if req._match_url(url_pattern) and req._complete:
                return req
        # Wait for future match
        future = asyncio.get_running_loop().create_future()
        self._waiters.append((url_pattern, future))
        return await asyncio.wait_for(future, timeout)

    def _on_request(self, params: dict):
        request_id = params["requestId"]
        req_data = params["request"]
        req = CapturedRequest(
            url=req_data["url"],
            method=req_data["method"],
            request_headers=req_data.get("headers", {}),
            _request_id=request_id,
            _session=self._session,
        )
        self._requests.append(req)
        self._by_id[request_id] = req
        if "timestamp" in params:
            self._request_timestamps[request_id] = params["timestamp"]

    def _on_response(self, params: dict):
        request_id = params["requestId"]
        req = self._by_id.get(request_id)
        if req:
            resp = params["response"]
            req.status = resp.get("status")
            req.headers = resp.get("headers", {})
            req.content_type = resp.get("mimeType", "")
            req.size = resp.get("encodedDataLength", 0)
            if self._logger:
                self._logger.log_response(req)

    def _on_finished(self, params: dict):
        request_id = params["requestId"]
        req = self._by_id.get(request_id)
        if req:
            req._complete = True
            # Calculate duration: (finished_timestamp - start_timestamp) * 1000
            start_ts = self._request_timestamps.get(request_id)
            end_ts = params.get("timestamp")
            if start_ts is not None and end_ts is not None:
                req.duration = (end_ts - start_ts) * 1000  # seconds -> ms
            # Clean up timestamp tracking
            self._request_timestamps.pop(request_id, None)
            # Notify waiters
            for pattern, future in self._waiters[:]:
                if req._match_url(pattern) and not future.done():
                    future.set_result(req)
                    self._waiters.remove((pattern, future))
