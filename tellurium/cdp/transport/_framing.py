"""Null-terminated message framing shared by the CDP pipe transports."""

from __future__ import annotations


class NullFramer:
    """Accumulates pipe chunks and splits them into ``\\0``-terminated messages.

    Only the bytes added since the last search are scanned, so a message
    that arrives in N chunks costs O(size), not O(size * N): a 50 MB reply
    (a full-page screenshot, a large response body) no longer stalls the
    event loop for close to a second.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._scanned = 0

    def feed(self, chunk: bytes) -> None:
        self._buffer += chunk

    def next_message(self) -> bytearray | None:
        """Pop the next complete message (without its terminator), or None."""
        end = self._buffer.find(b"\0", self._scanned)
        if end == -1:
            self._scanned = len(self._buffer)
            return None
        message = self._buffer[:end]
        del self._buffer[: end + 1]
        self._scanned = 0
        return message
