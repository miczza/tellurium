"""GeoIP resolution for proxy-based locale detection."""
from __future__ import annotations
from dataclasses import dataclass
import logging

logger = logging.getLogger("tellurium")


@dataclass
class GeoResult:
    country: str
    timezone: str
    languages: list[str]


COUNTRY_TIMEZONES = {
    "US": "America/New_York", "GB": "Europe/London", "DE": "Europe/Berlin",
    "FR": "Europe/Paris", "IT": "Europe/Rome", "ES": "Europe/Madrid",
    "NL": "Europe/Amsterdam", "BE": "Europe/Brussels", "AT": "Europe/Vienna",
    "CH": "Europe/Zurich", "SE": "Europe/Stockholm", "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen", "FI": "Europe/Helsinki", "PL": "Europe/Warsaw",
    "CZ": "Europe/Prague", "PT": "Europe/Lisbon", "IE": "Europe/Dublin",
    "RO": "Europe/Bucharest", "HU": "Europe/Budapest", "GR": "Europe/Athens",
    "JP": "Asia/Tokyo", "KR": "Asia/Seoul", "CN": "Asia/Shanghai",
    "IN": "Asia/Kolkata", "AU": "Australia/Sydney", "NZ": "Pacific/Auckland",
    "BR": "America/Sao_Paulo", "MX": "America/Mexico_City",
    "CA": "America/Toronto", "RU": "Europe/Moscow", "UA": "Europe/Kiev",
    "TR": "Europe/Istanbul", "IL": "Asia/Jerusalem", "AE": "Asia/Dubai",
    "SG": "Asia/Singapore", "HK": "Asia/Hong_Kong", "TW": "Asia/Taipei",
    "TH": "Asia/Bangkok", "VN": "Asia/Ho_Chi_Minh", "PH": "Asia/Manila",
    "ID": "Asia/Jakarta", "MY": "Asia/Kuala_Lumpur",
    "AR": "America/Argentina/Buenos_Aires", "CL": "America/Santiago",
    "CO": "America/Bogota", "ZA": "Africa/Johannesburg",
}

COUNTRY_LANGUAGES = {
    "US": ["en-US", "en"], "GB": ["en-GB", "en"], "DE": ["de-DE", "en"],
    "FR": ["fr-FR", "en"], "IT": ["it-IT", "en"], "ES": ["es-ES", "en"],
    "NL": ["nl-NL", "en"], "BE": ["nl-BE", "fr-BE", "en"],
    "AT": ["de-AT", "en"], "CH": ["de-CH", "fr-CH", "en"],
    "SE": ["sv-SE", "en"], "NO": ["nb-NO", "en"], "DK": ["da-DK", "en"],
    "FI": ["fi-FI", "en"], "PL": ["pl-PL", "en"], "CZ": ["cs-CZ", "en"],
    "PT": ["pt-PT", "en"], "IE": ["en-IE", "en"], "RO": ["ro-RO", "en"],
    "HU": ["hu-HU", "en"], "GR": ["el-GR", "en"],
    "JP": ["ja-JP", "en"], "KR": ["ko-KR", "en"], "CN": ["zh-CN", "en"],
    "IN": ["hi-IN", "en-IN", "en"], "AU": ["en-AU", "en"],
    "NZ": ["en-NZ", "en"], "BR": ["pt-BR", "en"], "MX": ["es-MX", "en"],
    "CA": ["en-CA", "fr-CA", "en"], "RU": ["ru-RU", "en"],
    "UA": ["uk-UA", "en"], "TR": ["tr-TR", "en"], "IL": ["he-IL", "en"],
    "AE": ["ar-AE", "en"], "SG": ["en-SG", "en"], "HK": ["zh-HK", "en"],
    "TW": ["zh-TW", "en"], "TH": ["th-TH", "en"], "VN": ["vi-VN", "en"],
    "PH": ["en-PH", "en"], "ID": ["id-ID", "en"], "MY": ["ms-MY", "en"],
    "AR": ["es-AR", "en"], "CL": ["es-CL", "en"], "CO": ["es-CO", "en"],
    "ZA": ["en-ZA", "en"],
}


_EXIT_IP_SERVICES = [
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
]


def resolve_exit_ip(proxy_url: str, forwarder_port: int | None = None) -> str:
    """Determine the real exit IP by making an HTTP request through the proxy.

    If a local ProxyForwarder is running (for authenticated proxies), uses
    ``localhost:<forwarder_port>`` as the HTTP proxy.  Otherwise builds a
    proxy handler from *proxy_url* directly (HTTP/HTTPS proxies only —
    SOCKS5 without auth falls back to DNS resolution of the proxy hostname).

    Tries multiple IP-echo services for reliability.
    """
    import socket
    import urllib.request

    # Build the opener with the right proxy
    if forwarder_port is not None:
        handler = urllib.request.ProxyHandler({
            "http": f"http://localhost:{forwarder_port}",
            "https": f"http://localhost:{forwarder_port}",
        })
    else:
        from urllib.parse import urlparse
        parsed = urlparse(proxy_url)
        if parsed.scheme in ("http", "https"):
            handler = urllib.request.ProxyHandler({
                "http": proxy_url,
                "https": proxy_url,
            })
        else:
            # SOCKS5 without auth: urllib doesn't support SOCKS natively.
            # Fallback: resolve proxy hostname via DNS.
            hostname = parsed.hostname or ""
            try:
                return socket.gethostbyname(hostname)
            except socket.gaierror:
                return hostname

    opener = urllib.request.build_opener(handler)

    for service_url in _EXIT_IP_SERVICES:
        try:
            req = urllib.request.Request(service_url, headers={"User-Agent": "curl/8.0"})
            with opener.open(req, timeout=10) as resp:
                ip = resp.read().decode().strip()
                if ip and all(c.isdigit() or c == "." for c in ip):
                    return ip
        except Exception:
            continue

    raise RuntimeError(
        "Could not determine exit IP through proxy. "
        "Tried: " + ", ".join(_EXIT_IP_SERVICES)
    )


def resolve_geoip(ip: str) -> GeoResult:
    """Resolve IP -> country -> timezone/languages. Requires maxminddb."""
    try:
        import maxminddb
    except ImportError:
        raise ImportError(
            "GeoIP requires maxminddb. Install with: pip install tellurium[geoip]"
        )

    db_path = _ensure_geolite2_db()
    with maxminddb.open_database(db_path) as reader:
        result = reader.get(ip)
        if not result or "country" not in result:
            raise ValueError(f"Could not resolve IP: {ip}")
        country = result["country"]["iso_code"]

    return GeoResult(
        country=country,
        timezone=COUNTRY_TIMEZONES.get(country, "America/New_York"),
        languages=COUNTRY_LANGUAGES.get(country, ["en-US", "en"]),
    )


def _ensure_geolite2_db() -> str:
    """Return path to GeoLite2 database. Download if needed."""
    from pathlib import Path
    db_dir = Path.home() / ".tellurium" / "geolite2"
    db_path = db_dir / "GeoLite2-Country.mmdb"
    if db_path.exists():
        return str(db_path)
    raise FileNotFoundError(
        f"GeoLite2 database not found at {db_path}. "
        "Download from MaxMind and place it there."
    )
