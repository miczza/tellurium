def test_session_importable_from_tellurium():
    from tellurium import Session
    assert Session is not None


def test_browser_still_exported():
    from tellurium import Browser
    assert Browser is not None


def test_cookie_still_exported():
    from tellurium import Cookie
    assert Cookie is not None
