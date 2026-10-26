from tellurium.browser.cookie import Cookie


def test_cookie_defaults():
    c = Cookie(name="sid", value="abc", domain=".example.com")
    assert c.path == "/"
    assert c.expires == -1
    assert c.http_only is False
    assert c.secure is False
    assert c.same_site == "Lax"


def test_cookie_to_json():
    c = Cookie(name="sid", value="abc", domain=".example.com", secure=True, http_only=True)
    j = c.to_json()
    assert j["name"] == "sid"
    assert j["secure"] is True
    assert j["httpOnly"] is True


def test_cookie_from_json():
    j = {
        "name": "sid",
        "value": "abc",
        "domain": ".example.com",
        "path": "/app",
        "secure": True,
        "httpOnly": False,
        "sameSite": "Strict",
    }
    c = Cookie.from_json(j)
    assert c.name == "sid"
    assert c.path == "/app"
    assert c.same_site == "Strict"


def test_cookie_from_json_minimal():
    j = {"name": "x", "value": "y", "domain": ".d.com"}
    c = Cookie.from_json(j)
    assert c.path == "/"


def test_cookie_to_netscape():
    c = Cookie(name="sid", value="abc", domain=".example.com", secure=True, expires=1742860800)
    line = c.to_netscape()
    parts = line.split("\t")
    assert parts[0] == ".example.com"
    assert parts[3] == "TRUE"
    assert parts[5] == "sid"
    assert parts[6] == "abc"


def test_cookies_save_load_json(tmp_path):
    cookies = [
        Cookie(name="a", value="1", domain=".example.com"),
        Cookie(name="b", value="2", domain=".test.com", secure=True),
    ]
    path = tmp_path / "cookies.json"
    Cookie.save_list(cookies, str(path), format="json")
    loaded = Cookie.load_list(str(path))
    assert len(loaded) == 2
    assert loaded[0].name == "a"
    assert loaded[1].secure is True


def test_cookies_save_load_netscape(tmp_path):
    cookies = [
        Cookie(name="sid", value="abc", domain=".example.com", secure=True, expires=1742860800),
    ]
    path = tmp_path / "cookies.txt"
    Cookie.save_list(cookies, str(path), format="netscape")
    loaded = Cookie.load_list(str(path), format="netscape")
    assert len(loaded) == 1
    assert loaded[0].name == "sid"
    assert loaded[0].secure is True


def test_cookies_load_autodetect_json(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text('[{"name":"x","value":"y","domain":".d.com"}]')
    loaded = Cookie.load_list(str(path))
    assert len(loaded) == 1


def test_cookies_load_autodetect_netscape(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text("# Netscape HTTP Cookie File\n.d.com\tTRUE\t/\tFALSE\t0\tx\ty\n")
    loaded = Cookie.load_list(str(path))
    assert len(loaded) == 1
    assert loaded[0].name == "x"


def test_netscape_httponly_prefix_is_imported(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        "#HttpOnly_.example.com\tTRUE\t/\tTRUE\t0\tauth\tsecret\n"
        ".example.com\tTRUE\t/\tFALSE\t0\tplain\tv\n"
    )
    loaded = Cookie.load_list(str(path))
    assert [(c.name, c.http_only) for c in loaded] == [("auth", True), ("plain", False)]
    assert loaded[0].domain == ".example.com"
    assert loaded[0].secure is True


def test_netscape_httponly_round_trip(tmp_path):
    path = tmp_path / "cookies.txt"
    cookie = Cookie(name="auth", value="secret", domain=".example.com", http_only=True)
    assert cookie.to_netscape().startswith("#HttpOnly_.example.com\t")
    Cookie.save_list([cookie], str(path), format="netscape")
    loaded = Cookie.load_list(str(path), format="netscape")
    assert len(loaded) == 1 and loaded[0].http_only is True


def test_matches_domain_is_not_a_substring_match():
    from tellurium.browser.cookie import matches_domain

    assert matches_domain(".example.com", "example.com")
    assert matches_domain("example.com", "example.com")
    assert matches_domain("sub.example.com", "example.com")
    assert matches_domain(".sub.example.com", ".example.com")
    assert not matches_domain("notexample.com", "example.com")
    assert not matches_domain(".notexample.com", "example.com")
    assert not matches_domain("example.com.evil.net", "example.com")
    assert not matches_domain("example.com", "sub.example.com")


def test_a_host_also_sees_the_parent_domain_cookies_it_receives():
    from tellurium.browser.cookie import matches_domain

    # ".example.com" is a domain cookie: sub.example.com receives it.
    assert matches_domain(".example.com", "sub.example.com", received=True)
    # A host-only cookie of example.com is not sent to sub.example.com.
    assert not matches_domain("example.com", "sub.example.com", received=True)
    assert not matches_domain(".other.example.com", "sub.example.com", received=True)
    assert not matches_domain(".com", "sub.example.com", received=False)


def test_a_dotless_domain_matches_only_itself():
    from tellurium.browser.cookie import matches_domain

    # An intranet host works...
    assert matches_domain("intranet", "intranet", received=True)
    assert matches_domain(".intranet", "intranet")
    # ...but never expands: "com" is not every .com site, nor their parent.
    assert not matches_domain(".example.com", "com", received=True)
    assert not matches_domain("example.com", "com")
    assert not matches_domain("wiki.intranet", "intranet")
    assert not matches_domain(".com", "example.com", received=True)


def test_localhost_and_ips_are_domains():
    from tellurium.browser.cookie import matches_domain

    assert matches_domain("localhost", "localhost")
    assert matches_domain("127.0.0.1", "127.0.0.1")


_PARTITION = {"topLevelSite": "https://other.test", "hasCrossSiteAncestor": True}


def test_cookie_json_keeps_the_partition():
    raw = {
        "name": "chips",
        "value": "1",
        "domain": "example.test",
        "path": "/",
        "expires": -1,
        "httpOnly": False,
        "secure": True,
        "sameSite": "None",
        "partitionKey": _PARTITION,
    }
    c = Cookie.from_json(raw)
    assert c.partition_key == _PARTITION
    assert c.to_json() == raw


def test_cookie_json_without_samesite_stays_without():
    raw = {"name": "x", "value": "y", "domain": "d.com", "path": "/", "expires": -1}
    c = Cookie.from_json({**raw, "httpOnly": False, "secure": False})
    assert c.same_site is None
    assert "sameSite" not in c.to_json()
    assert "partitionKey" not in c.to_json()
