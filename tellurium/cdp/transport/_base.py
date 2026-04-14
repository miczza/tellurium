"""Abstract base class for CDP transports."""

import abc


class CDPTransport(abc.ABC):
    """Interface for CDP message transport.

    Implementations send and receive null-terminated JSON messages
    over a communication channel (pipe, websocket, etc.).
    """

    @abc.abstractmethod
    async def send(self, data: bytes) -> None:
        """Send a JSON message (already encoded as bytes with null terminator)."""

    @abc.abstractmethod
    async def recv(self) -> dict:
        """Receive the next JSON message (blocking). Returns parsed dict."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Close the transport."""
