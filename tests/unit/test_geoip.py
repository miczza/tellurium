from unittest.mock import MagicMock, patch

import pytest

from tellurium.stealth.geoip import (
    COUNTRY_LANGUAGES,
    COUNTRY_TIMEZONES,
    GeoResult,
    _ensure_geolite2_db,
    resolve_exit_ip,
    resolve_geoip,
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


class FakeVia:
    """Stands for the proxy tunnel: answers by URL, records the requests."""

    def __init__(self, answers: dict[str, object]):
        self.answers = answers
        self.urls: list[str] = []

    def get(self, url, timeout):
        self.urls.append(url)
        answer = self.answers.get(url, OSError("unreachable"))
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def via(monkeypatch):
    """Every tunnel built by the module is this fake one."""
    from tellurium.stealth import geoip

    fake = FakeVia({})
    built: list[tuple] = []
    real_of = geoip._HttpProxy.of

    def of(proxy_url, forwarder_port):
        built.append((real_of(proxy_url, forwarder_port), proxy_url, forwarder_port))
        return fake if built[-1][0] is not None else None

    monkeypatch.setattr(geoip._HttpProxy, "of", staticmethod(of))
    fake.built = built
    return fake


def test_resolve_geoip_online_fallback_goes_through_the_proxy(via):
    """No maxminddb: the online country lookup is tunnelled through the proxy."""
    via.answers = {"https://ipapi.co/8.8.8.8/country/": "DE"}
    with patch.dict("sys.modules", {"maxminddb": None}):
        geo = resolve_geoip("8.8.8.8", proxy="http://127.0.0.1:3128")
    assert geo.country == "DE" and geo.timezone == "Europe/Berlin"
    assert via.urls == ["https://ipapi.co/8.8.8.8/country/"]


@pytest.mark.parametrize("proxy", [None, "socks5://127.0.0.1:1080", "https://127.0.0.1:3128"])
def test_no_online_lookup_without_a_proxy_to_tunnel_through(via, proxy):
    with patch.dict("sys.modules", {"maxminddb": None}):
        with pytest.raises(ImportError):
            resolve_geoip("8.8.8.8", proxy=proxy)
    assert via.urls == []


def test_online_country_parses_text_and_json():
    from tellurium.stealth import geoip

    assert (
        geoip._online_country("1.1.1.1", FakeVia({"https://ipapi.co/1.1.1.1/country/": "it"}))
        == "IT"
    )
    fake = FakeVia({"https://api.country.is/1.1.1.1": '{"ip":"1.1.1.1","country":"fr"}'})
    assert geoip._online_country("1.1.1.1", fake) == "FR"


def test_http_proxy_of_picks_forwarder_or_plain_http_proxy():
    from tellurium.stealth.geoip import _HttpProxy

    assert _HttpProxy.of("http://u:p@proxy:8080", 9999) == _HttpProxy("127.0.0.1", 9999)
    assert _HttpProxy.of("http://proxy.example.com:3128", None) == _HttpProxy(
        "proxy.example.com", 3128
    )
    with_auth = _HttpProxy.of("http://u:p@proxy:8080", None)
    assert with_auth.authorization == "Basic dTpw"
    assert _HttpProxy.of("socks5://proxy:1080", None) is None
    assert _HttpProxy.of(None, None) is None


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

    with (
        patch.dict("sys.modules", {"maxminddb": mock_maxminddb}),
        patch("tellurium.stealth.geoip._ensure_geolite2_db", return_value="/fake/path.mmdb"),
    ):
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

    with (
        patch.dict("sys.modules", {"maxminddb": mock_maxminddb}),
        patch("tellurium.stealth.geoip._ensure_geolite2_db", return_value="/fake/path.mmdb"),
    ):
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

    with (
        patch.dict("sys.modules", {"maxminddb": mock_maxminddb}),
        patch("tellurium.stealth.geoip._ensure_geolite2_db", return_value="/fake/path.mmdb"),
    ):
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

    with (
        patch.dict("sys.modules", {"maxminddb": mock_maxminddb}),
        patch("tellurium.stealth.geoip._ensure_geolite2_db", return_value="/fake/path.mmdb"),
    ):
        with pytest.raises(ValueError, match="Could not resolve IP"):
            resolve_geoip("1.2.3.4")


# ---------------------------------------------------------------------------
# resolve_exit_ip
# ---------------------------------------------------------------------------


def test_resolve_exit_ip_goes_through_the_proxy(via):
    via.answers = {"https://api.ipify.org": "203.0.113.42"}
    ip = resolve_exit_ip("http://user:pass@proxy:8080", forwarder_port=9999)
    assert ip == "203.0.113.42"
    assert via.built[0][2] == 9999


def test_resolve_exit_ip_socks5_no_forwarder_fallback(via):
    """SOCKS5 without forwarder: DNS of the proxy host, no request at all."""
    with patch("socket.gethostbyname", return_value="192.0.2.1"):
        ip = resolve_exit_ip("socks5://socks.example.com:1080")
    assert ip == "192.0.2.1"
    assert via.urls == []


def test_resolve_exit_ip_all_services_fail(via):
    with pytest.raises(RuntimeError, match="Could not determine exit IP"):
        resolve_exit_ip("http://proxy:8080", forwarder_port=9999)
    assert len(via.urls) == 4


def test_resolve_exit_ip_tries_next_service_on_failure(via):
    via.answers = {"https://checkip.amazonaws.com": "203.0.113.1\n".strip()}
    ip = resolve_exit_ip("http://proxy:8080", forwarder_port=9999)
    assert ip == "203.0.113.1"
    assert len(via.urls) == 2


def test_resolve_exit_ip_stops_at_the_deadline(via):
    import time

    with pytest.raises(TimeoutError):
        resolve_exit_ip("http://proxy:8080", 9999, deadline=time.monotonic() - 1)
    assert via.urls == []


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
        def read(self):
            return gzip.compress(b"MMDB")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

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
