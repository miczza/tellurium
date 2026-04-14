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
    """Should raise ImportError when maxminddb is not installed."""
    with patch.dict("sys.modules", {"maxminddb": None}):
        with pytest.raises(ImportError, match="maxminddb"):
            resolve_geoip("8.8.8.8")


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

def test_ensure_geolite2_db_not_found():
    """Should raise FileNotFoundError when database doesn't exist."""
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError, match="GeoLite2 database not found"):
            _ensure_geolite2_db()


def test_ensure_geolite2_db_found():
    """Should return path when database exists."""
    with patch("pathlib.Path.exists", return_value=True):
        result = _ensure_geolite2_db()
        assert "GeoLite2-Country.mmdb" in result
        assert ".tellurium" in result
