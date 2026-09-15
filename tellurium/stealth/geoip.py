"""GeoIP resolution for proxy-based locale detection."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("tellurium")


@dataclass
class GeoResult:
    country: str
    timezone: str
    languages: list[str]


COUNTRY_TIMEZONES = {
    "US": "America/New_York",
    "GB": "Europe/London",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "IT": "Europe/Rome",
    "ES": "Europe/Madrid",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "AT": "Europe/Vienna",
    "CH": "Europe/Zurich",
    "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "PL": "Europe/Warsaw",
    "CZ": "Europe/Prague",
    "PT": "Europe/Lisbon",
    "IE": "Europe/Dublin",
    "RO": "Europe/Bucharest",
    "HU": "Europe/Budapest",
    "GR": "Europe/Athens",
    "JP": "Asia/Tokyo",
    "KR": "Asia/Seoul",
    "CN": "Asia/Shanghai",
    "IN": "Asia/Kolkata",
    "AU": "Australia/Sydney",
    "NZ": "Pacific/Auckland",
    "BR": "America/Sao_Paulo",
    "MX": "America/Mexico_City",
    "CA": "America/Toronto",
    "RU": "Europe/Moscow",
    "UA": "Europe/Kiev",
    "TR": "Europe/Istanbul",
    "IL": "Asia/Jerusalem",
    "AE": "Asia/Dubai",
    "SG": "Asia/Singapore",
    "HK": "Asia/Hong_Kong",
    "TW": "Asia/Taipei",
    "TH": "Asia/Bangkok",
    "VN": "Asia/Ho_Chi_Minh",
    "PH": "Asia/Manila",
    "ID": "Asia/Jakarta",
    "MY": "Asia/Kuala_Lumpur",
    "AR": "America/Argentina/Buenos_Aires",
    "CL": "America/Santiago",
    "CO": "America/Bogota",
    "ZA": "Africa/Johannesburg",
}

COUNTRY_LANGUAGES = {
    "US": ["en-US", "en"],
    "GB": ["en-GB", "en"],
    "DE": ["de-DE", "en"],
    "FR": ["fr-FR", "en"],
    "IT": ["it-IT", "en"],
    "ES": ["es-ES", "en"],
    "NL": ["nl-NL", "en"],
    "BE": ["nl-BE", "fr-BE", "en"],
    "AT": ["de-AT", "en"],
    "CH": ["de-CH", "fr-CH", "en"],
    "SE": ["sv-SE", "en"],
    "NO": ["nb-NO", "en"],
    "DK": ["da-DK", "en"],
    "FI": ["fi-FI", "en"],
    "PL": ["pl-PL", "en"],
    "CZ": ["cs-CZ", "en"],
    "PT": ["pt-PT", "en"],
    "IE": ["en-IE", "en"],
    "RO": ["ro-RO", "en"],
    "HU": ["hu-HU", "en"],
    "GR": ["el-GR", "en"],
    "JP": ["ja-JP", "en"],
    "KR": ["ko-KR", "en"],
    "CN": ["zh-CN", "en"],
    "IN": ["hi-IN", "en-IN", "en"],
    "AU": ["en-AU", "en"],
    "NZ": ["en-NZ", "en"],
    "BR": ["pt-BR", "en"],
    "MX": ["es-MX", "en"],
    "CA": ["en-CA", "fr-CA", "en"],
    "RU": ["ru-RU", "en"],
    "UA": ["uk-UA", "en"],
    "TR": ["tr-TR", "en"],
    "IL": ["he-IL", "en"],
    "AE": ["ar-AE", "en"],
    "SG": ["en-SG", "en"],
    "HK": ["zh-HK", "en"],
    "TW": ["zh-TW", "en"],
    "TH": ["th-TH", "en"],
    "VN": ["vi-VN", "en"],
    "PH": ["en-PH", "en"],
    "ID": ["id-ID", "en"],
    "MY": ["ms-MY", "en"],
    "AR": ["es-AR", "en"],
    "CL": ["es-CL", "en"],
    "CO": ["es-CO", "en"],
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
        handler = urllib.request.ProxyHandler(
            {
                "http": f"http://localhost:{forwarder_port}",
                "https": f"http://localhost:{forwarder_port}",
            }
        )
    else:
        from urllib.parse import urlparse

        parsed = urlparse(proxy_url)
        if parsed.scheme in ("http", "https"):
            handler = urllib.request.ProxyHandler(
                {
                    "http": proxy_url,
                    "https": proxy_url,
                }
            )
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
        except Exception:  # noqa: BLE001 - try next service
            continue

    raise RuntimeError(
        "Could not determine exit IP through proxy. Tried: " + ", ".join(_EXIT_IP_SERVICES)
    )


_ONLINE_COUNTRY_SERVICES = [
    "https://ipapi.co/{ip}/country/",
    "https://api.country.is/{ip}",
]


def _online_country(ip: str, timeout: float = 5) -> str | None:
    """Best-effort online IP -> ISO country lookup (no DB required)."""
    import json
    import urllib.request

    for template in _ONLINE_COUNTRY_SERVICES:
        url = template.format(ip=ip)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode().strip()
        except Exception as e:  # noqa: BLE001 - try next service
            logger.debug("online geoip %s failed: %s", url, e)
            continue
        code = body
        if body.startswith("{"):
            try:
                code = json.loads(body).get("country", "")
            except ValueError:
                code = ""
        code = code.strip().upper()
        if len(code) == 2 and code.isalpha():
            return code
    return None


def _geo_from_country(country: str) -> GeoResult:
    return GeoResult(
        country=country,
        timezone=COUNTRY_TIMEZONES.get(country, "America/New_York"),
        languages=COUNTRY_LANGUAGES.get(country, ["en-US", "en"]),
    )


def resolve_geoip(ip: str, *, online_fallback: bool = True) -> GeoResult:
    """Resolve IP -> country -> timezone/languages.

    Uses a local MMDB database (``tellurium download-geoip``, MaxMind GeoLite2
    or DB-IP Lite) via ``maxminddb``. When neither the module nor a database is
    available and *online_fallback* is true, falls back to a public IP-to-country
    web service (one HTTPS request; same trust class as the exit-IP echo).
    """
    try:
        import maxminddb
    except ImportError:
        maxminddb = None

    if maxminddb is not None:
        try:
            db_path = _ensure_geolite2_db()
        except FileNotFoundError:
            db_path = None
        if db_path is not None:
            with maxminddb.open_database(db_path) as reader:
                result = reader.get(ip)
                if not result or "country" not in result:
                    raise ValueError(f"Could not resolve IP: {ip}")
                return _geo_from_country(result["country"]["iso_code"])

    if online_fallback:
        code = _online_country(ip)
        if code:
            logger.warning(
                "GeoIP: no local database, resolved %s -> %s online. "
                "Run `tellurium download-geoip` for offline lookups.",
                ip,
                code,
            )
            return _geo_from_country(code)

    if maxminddb is None:
        raise ImportError("GeoIP requires maxminddb. Install with: pip install tellurium[geoip]")
    _ensure_geolite2_db()  # raises FileNotFoundError with instructions
    raise ValueError(f"Could not resolve IP: {ip}")


_DB_DIR_NAME = "geolite2"
_DB_CANDIDATES = ("GeoLite2-Country.mmdb", "dbip-country-lite.mmdb", "GeoLite2-City.mmdb")


def _geoip_dir():

    from tellurium.browser._cache import tellurium_home

    return tellurium_home() / _DB_DIR_NAME


def _ensure_geolite2_db() -> str:
    """Return path to a country MMDB database, or raise FileNotFoundError.

    Search order: ``$TELLURIUM_GEOIP_DB``, then ``~/.tellurium/geolite2/``
    (``GeoLite2-Country.mmdb``, ``dbip-country-lite.mmdb``, ``GeoLite2-City.mmdb``).
    """
    import os
    from pathlib import Path

    env = os.environ.get("TELLURIUM_GEOIP_DB")
    if env and Path(env).exists():
        return env
    db_dir = _geoip_dir()
    for name in _DB_CANDIDATES:
        db_path = db_dir / name
        if db_path.exists():
            return str(db_path)
    raise FileNotFoundError(
        f"GeoLite2 database not found at {db_dir / _DB_CANDIDATES[0]}. "
        "Run `tellurium download-geoip` (DB-IP Lite, no account) or "
        "`tellurium download-geoip --maxmind-license-key KEY`, or set TELLURIUM_GEOIP_DB."
    )


def download_geoip_db(*, maxmind_license_key: str | None = None, dest_dir=None) -> str:
    """Download a country MMDB database into ``~/.tellurium/geolite2/``.

    Without a key: DB-IP Country Lite (CC BY 4.0, https://db-ip.com/db/lite.php).
    With ``maxmind_license_key``: MaxMind GeoLite2-Country (free account).
    Returns the path of the installed database.
    """
    import gzip
    import io
    import shutil
    import tarfile
    import urllib.error
    import urllib.request
    from datetime import date
    from pathlib import Path

    dest_dir = Path(dest_dir) if dest_dir else _geoip_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)

    if maxmind_license_key:
        url = (
            "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country"
            f"&license_key={maxmind_license_key}&suffix=tar.gz"
        )
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
            data = resp.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            member = next((m for m in tf.getmembers() if m.name.endswith(".mmdb")), None)
            if member is None:
                raise RuntimeError("MaxMind archive contains no .mmdb file")
            src = tf.extractfile(member)
            dest = dest_dir / "GeoLite2-Country.mmdb"
            with open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
        logger.info("GeoLite2-Country installed at %s", dest)
        return str(dest)

    today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(3):
        months.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    last_err: Exception | None = None
    for ym in months:
        url = f"https://download.db-ip.com/free/dbip-country-lite-{ym}.mmdb.gz"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
                data = resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 404:
                continue
            raise
        dest = dest_dir / "dbip-country-lite.mmdb"
        dest.write_bytes(gzip.decompress(data))
        logger.info("DB-IP Country Lite (%s) installed at %s", ym, dest)
        return str(dest)
    raise RuntimeError(f"Could not download DB-IP Country Lite (tried {months}): {last_err}")
