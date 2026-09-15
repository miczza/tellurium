import pytest
from unittest.mock import patch, MagicMock

from tellurium.stealth.geoip import (
    GeoResult,
    COUNTRY_TIMEZONES,
    COUNTRY_LANGUAGES,
    resolve_geoip,
    resolve_exit_ip,
    _ensure_geolite2_db,
)


# ---------------------------------------------------------------------------
# GeoResult dataclass
# ---------------------------------------------------------------------------

def test_geo_result_fields():
    r = GeoResult(country="US", timezone="America/New_York", languages=["en-US", "en"])
    assert r.country == "US"
    assert r.timezone == "America/New_York"
    assert r.languages == ["en-US", "en"]


def test_geo_result_equality():
    a = GeoResult(country="DE", timezone="Europe/Berlin", languages=["de-DE", "en"])
    b = GeoResult(country="DE", timezone="Europe/Berlin", languages=["de-DE", "en"])
    assert a == b


# ---------------------------------------------------------------------------
# Country lookup tables
# ---------------------------------------------------------------------------

def test_country_timezones_coverage():
    # Spot-check important countries
    assert COUNTRY_TIMEZONES["US"] == "America/New_York"
    assert COUNTRY_TIMEZONES["GB"] == "Europe/London"
    assert COUNTRY_TIMEZONES["JP"] == "Asia/Tokyo"
    assert COUNTRY_TIMEZONES["DE"] == "Europe/Berlin"
    assert COUNTRY_TIMEZONES["BR"] == "America/Sao_Paulo"
    assert COUNTRY_TIMEZONES["AU"] == "Australia/Sydney"


def test_country_languages_coverage():
    assert COUNTRY_LANGUAGES["US"] == ["en-US", "en"]
    assert COUNTRY_LANGUAGES["FR"] == ["fr-FR", "en"]
    assert COUNTRY_LANGUAGES["JP"] == ["ja-JP", "en"]
    assert "en" in COUNTRY_LANGUAGES["DE"]


def test_country_tables_same_keys():
    """Both tables should cover the same set of countries."""
    assert set(COUNTRY_TIMEZONES.keys()) == set(COUNTRY_LANGUAGES.keys())


def test_all_languages_lists_end_with_en():
    """Every language list should end with 'en' as fallback."""
    for country, langs in COUNTRY_LANGUAGES.items():
        assert langs[-1] == "en", f"{country} languages don't end with 'en': {langs}"


# ---------------------------------------------------------------------------
# resolve_geoip
# ---------------------------------------------------------------------------

def test_resolve_geoip_missing_maxminddb():
    """Without maxminddb and with the online fallback disabled -> ImportError."""
    with patch.dict("sys.modules", {"maxminddb": None}):
        with pytest.raises(ImportError, match="maxminddb"):
            resolve_geoip("8.8.8.8", online_fallback=False)


def test_resolve_geoip_online_fallback_without_db(monkeypatch):
    """No maxminddb: fall back to an online country lookup."""
    monkeypatch.setattr("tellurium.stealth.geoip._online_country", lambda ip, timeout=5: "DE")
    with patch.dict("sys.modules", {"maxminddb": None}):
        geo = resolve_geoip("8.8.8.8")
    assert geo.country == "DE" and geo.timezone == "Europe/Berlin"


def test_online_country_parses_text_and_json(monkeypatch):
    from tellurium.stealth import geoip
    bodies = iter([b"  it\n"])

    class R:
        def __init__(self, b): self.b = b
        def read(self): return self.b
        def __enter__(self): return self
        def __exit__(self, *a): return None

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=5: R(next(bodies)))
    assert geoip._online_country("1.1.1.1") == "IT"
    bodies = iter([b'{"ip":"1.1.1.1","country":"fr"}'])
    assert geoip._online_country("1.1.1.1") == "FR"


def test_resolve_geoip_success():
    """Mock maxminddb to test the resolution logic."""
    mock_reader = MagicMock()
    mock_reader.get.return_value = {
        "country": {"iso_code": "DE"},
    }
    mock_reader.__enter__ = MagicMock(return_value=mock_reader)
    mock_reader.__exit__ = MagicMock(return_value=False)

    mock_maxminddb = MagicMock()
    mock_maxminddb.open_database.return_value = mock_reader

    with patch.dict("sys.modules", {"maxminddb": mock_maxminddb}), \
         patch("tellurium.stealth.geoip._ensure_geolite2_db", return_value="/fake/path.mmdb"):
        result = resolve_geoip("1.2.3.4")

    assert result.country == "DE"
    assert result.timezone == "Europe/Berlin"
    assert result.languages == ["de-DE", "en"]


def test_resolve_geoip_unknown_country_defaults():
    """Unknown country should fall back to US defaults."""
    mock_reader = MagicMock()
    mock_reader.get.return_value = {
        "country": {"iso_code": "XX"},
    }
    mock_reader.__enter__ = MagicMock(return_value=mock_reader)
    mock_reader.__exit__ = MagicMock(return_value=False)

    mock_maxminddb = MagicMock()
    mock_maxminddb.open_database.return_value = mock_reader

    with patch.dict("sys.modules", {"maxminddb": mock_maxminddb}), \
         patch("tellurium.stealth.geoip._ensure_geolite2_db", return_value="/fake/path.mmdb"):
        result = resolve_geoip("1.2.3.4")

    assert result.country == "XX"
    assert result.timezone == "America/New_York"
    assert result.languages == ["en-US", "en"]


def test_resolve_geoip_no_country_in_result():
    """Should raise ValueError when result has no country data."""
    mock_reader = MagicMock()
    mock_reader.get.return_value = {"location": {"time_zone": "Europe/Berlin"}}
    mock_reader.__enter__ = MagicMock(return_value=mock_reader)
    mock_reader.__exit__ = MagicMock(return_value=False)

    mock_maxminddb = MagicMock()
    mock_maxminddb.open_database.return_value = mock_reader

    with patch.dict("sys.modules", {"maxminddb": mock_maxminddb}), \
         patch("tellurium.stealth.geoip._ensure_geolite2_db", return_value="/fake/path.mmdb"):
        with pytest.raises(ValueError, match="Could not resolve IP"):
            resolve_geoip("1.2.3.4")


def test_resolve_geoip_none_result():
    """Should raise ValueError when reader returns None."""
    mock_reader = MagicMock()
    mock_reader.get.return_value = None
    mock_reader.__enter__ = MagicMock(return_value=mock_reader)
    mock_reader.__exit__ = MagicMock(return_value=False)

    mock_maxminddb = MagicMock()
    mock_maxminddb.open_database.return_value = mock_reader

    with patch.dict("sys.modules", {"maxminddb": mock_maxminddb}), \
         patch("tellurium.stealth.geoip._ensure_geolite2_db", return_value="/fake/path.mmdb"):
        with pytest.raises(ValueError, match="Could not resolve IP"):
            resolve_geoip("1.2.3.4")


# ---------------------------------------------------------------------------
# resolve_exit_ip
# ---------------------------------------------------------------------------

def test_resolve_exit_ip_with_forwarder():
    """When a forwarder port is given, it should use localhost as HTTP proxy."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"203.0.113.42"
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_opener = MagicMock()
    mock_opener.open.return_value = mock_response

    with patch("urllib.request.build_opener", return_value=mock_opener) as mock_build:
        ip = resolve_exit_ip("http://user:pass@proxy:8080", forwarder_port=9999)

    assert ip == "203.0.113.42"
    # Verify ProxyHandler was created with localhost
    handler_arg = mock_build.call_args[0][0]
    assert "localhost:9999" in str(handler_arg.proxies)


def test_resolve_exit_ip_http_no_forwarder():
    """HTTP proxy without auth should use proxy URL directly."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"198.51.100.10\n"
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_opener = MagicMock()
    mock_opener.open.return_value = mock_response

    with patch("urllib.request.build_opener", return_value=mock_opener):
        ip = resolve_exit_ip("http://proxy.example.com:3128")

    assert ip == "198.51.100.10"


def test_resolve_exit_ip_socks5_no_forwarder_fallback():
    """SOCKS5 without forwarder should fall back to DNS resolution."""
    with patch("socket.gethostbyname", return_value="192.0.2.1"):
        ip = resolve_exit_ip("socks5://socks.example.com:1080")

    assert ip == "192.0.2.1"


def test_resolve_exit_ip_all_services_fail():
    """Should raise RuntimeError when all IP services fail."""
    mock_opener = MagicMock()
    mock_opener.open.side_effect = Exception("connection refused")

    with patch("urllib.request.build_opener", return_value=mock_opener):
        with pytest.raises(RuntimeError, match="Could not determine exit IP"):
            resolve_exit_ip("http://proxy:8080", forwarder_port=9999)


def test_resolve_exit_ip_tries_next_service_on_failure():
    """Should try the next service when one fails."""
    mock_response = MagicMock()
    mock_response.read.return_value = b"203.0.113.1"
    mock_response.__enter__ = MagicMock(return_value=mock_response)
    mock_response.__exit__ = MagicMock(return_value=False)

    mock_opener = MagicMock()
    mock_opener.open.side_effect = [
        Exception("timeout"),      # first service fails
        mock_response,             # second service succeeds
    ]

    with patch("urllib.request.build_opener", return_value=mock_opener):
        ip = resolve_exit_ip("http://proxy:8080", forwarder_port=9999)

    assert ip == "203.0.113.1"
    assert mock_opener.open.call_count == 2


# ---------------------------------------------------------------------------
# _ensure_geolite2_db
# ---------------------------------------------------------------------------

def test_ensure_geolite2_db_not_found(tmp_path, monkeypatch):
    monkeypatch.delenv("TELLURIUM_GEOIP_DB", raising=False)
    monkeypatch.setattr("tellurium.stealth.geoip._geoip_dir", lambda: tmp_path)
    with pytest.raises(FileNotFoundError, match="download-geoip"):
        _ensure_geolite2_db()


def test_ensure_geolite2_db_found(tmp_path, monkeypatch):
    monkeypatch.delenv("TELLURIUM_GEOIP_DB", raising=False)
    monkeypatch.setattr("tellurium.stealth.geoip._geoip_dir", lambda: tmp_path)
    (tmp_path / "dbip-country-lite.mmdb").write_bytes(b"x")
    assert _ensure_geolite2_db().endswith("dbip-country-lite.mmdb")
    (tmp_path / "GeoLite2-Country.mmdb").write_bytes(b"x")
    assert _ensure_geolite2_db().endswith("GeoLite2-Country.mmdb")


def test_ensure_geolite2_db_env_override(tmp_path, monkeypatch):
    db = tmp_path / "custom.mmdb"
    db.write_bytes(b"x")
    monkeypatch.setenv("TELLURIUM_GEOIP_DB", str(db))
    assert _ensure_geolite2_db() == str(db)


def test_download_geoip_db_dbip(tmp_path, monkeypatch):
    import gzip
    import urllib.error
    from tellurium.stealth.geoip import download_geoip_db
    seen = []

    class R:
        def read(self): return gzip.compress(b"MMDB")
        def __enter__(self): return self
        def __exit__(self, *a): return None

    def urlopen(url, timeout=60):
        seen.append(url)
        if len(seen) == 1:  # current month not published yet -> 404
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        return R()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    path = download_geoip_db(dest_dir=tmp_path)
    assert path.endswith("dbip-country-lite.mmdb")
    assert (tmp_path / "dbip-country-lite.mmdb").read_bytes() == b"MMDB"
    assert len(seen) == 2 and "download.db-ip.com" in seen[0]
