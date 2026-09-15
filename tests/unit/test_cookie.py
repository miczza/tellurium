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
