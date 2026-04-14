import pytest
from unittest.mock import patch, MagicMock

from tellurium.stealth.geoip import (
    GeoResult,
    COUNTRY_TIMEZONES,
    COUNTRY_LANGUAGES,
    resolve_geoip,
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
