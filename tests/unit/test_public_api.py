def test_session_importable_from_tellurium():
    from tellurium import Session
    assert Session is not None


def test_browser_still_exported():
    from tellurium import Browser
    assert Browser is not None


def test_cookie_still_exported():
    from tellurium import Cookie
    assert Cookie is not None


def test_tab_exported():
    """Tab should be importable from tellurium."""
    from tellurium import Tab
    assert Tab is not None


def test_element_exported():
    """Element should be importable from tellurium."""
    from tellurium import Element
    assert Element is not None


def test_captured_request_exported():
    """CapturedRequest should be importable from tellurium."""
    from tellurium import CapturedRequest
    assert CapturedRequest is not None


def test_intercepted_request_exported():
    """InterceptedRequest should be importable from tellurium."""
    from tellurium import InterceptedRequest
    assert InterceptedRequest is not None
