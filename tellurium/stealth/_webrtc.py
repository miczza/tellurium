"""WebRTC public-IP resolution for --fingerprint-webrtc-ip.

Accepts three forms:
- 'disable'        → None (no spoofing; native patch off, webrtc.js no-op)
- 'auto'           → resolve the proxy hostname to an IP via DNS
- '<ip literal>'   → IPv4 or IPv6 string, passed through verbatim

Native patch T3.5 consumes this IP; webrtc.js (stock mode fallback)
also consumes it via the {{WEBRTC_PUBLIC_IP}} placeholder.

Note: in stock mode, webrtc.js rewrites only IPv4 candidates; an IPv6
SPOOF_IP only takes effect via the native patch (PatchedEngine).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def resolve_webrtc_ip(setting: str, *, proxy: str | None) -> str | None:
    """Return the public IP to advertise via ICE, or None if disabled.

    'auto' does a blocking DNS lookup: off the event loop.
    """
    if setting == "disable":
        return None

    if setting == "auto":
        if not proxy:
            raise ValueError(
                "webrtc_ip='auto' requires proxy=<url> so the proxy's "
                "egress IP can be resolved. Pass an explicit IP or "
                "use 'disable' if no proxy is configured."
            )
        parsed = urlparse(proxy)
        host = parsed.hostname
        if not host:
            # Not the URL itself: it may carry the proxy's password.
            raise ValueError(
                f"Could not parse a host name from the {parsed.scheme or 'proxy'} proxy URL "
                "for webrtc_ip='auto'"
            )
        try:
            return socket.gethostbyname(host)
        except OSError as e:
            raise ValueError(
                f"Could not resolve proxy host {host!r} for webrtc_ip='auto': {e}"
            ) from e

    try:
        ipaddress.ip_address(setting)
    except ValueError:
        raise ValueError(
            f"invalid webrtc_ip={setting!r}: must be 'disable', 'auto', "
            f"or a valid IPv4/IPv6 literal"
        ) from None
    return setting
