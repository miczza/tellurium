from tellurium.cdp.types import CDPError, T_JSON_DICT


def test_cdp_error_with_code():
    err = CDPError("Target not found", code=-32602)
    assert "Target not found" in str(err)
    assert "-32602" in str(err)
    assert err.message == "Target not found"
    assert err.code == -32602


def test_cdp_error_without_code():
    err = CDPError("Something failed")
    assert str(err) == "Something failed"
    assert err.message == "Something failed"
    assert err.code is None


def test_cdp_error_is_exception():
    try:
        raise CDPError("test", code=1)
    except CDPError as e:
        assert e.message == "test"
    except Exception:
        raise AssertionError("CDPError should be catchable as CDPError")


def test_t_json_dict_is_dict():
    d: T_JSON_DICT = {"method": "Page.navigate", "params": {"url": "https://example.com"}}
    assert isinstance(d, dict)
    assert d["method"] == "Page.navigate"
