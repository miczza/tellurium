from tellurium.browser.engine import StockEngine, PatchedEngine


def test_stock_engine_capabilities_empty():
    engine = StockEngine()
    assert engine.capabilities() == set()


def test_stock_engine_build_args_empty():
    engine = StockEngine()
    assert engine.build_args(None) == []


def test_patched_engine_capabilities():
    engine = PatchedEngine()
    caps = engine.capabilities()
    assert "native_fingerprint" in caps
    assert "native_client_hints" in caps
    assert "native_cdp_fix" in caps
    assert "native_network_timing" in caps
    assert "native_navigator" in caps


def test_patched_engine_build_args_no_profile():
    engine = PatchedEngine()
    assert engine.build_args(None) == []


def test_patched_engine_build_args_with_seed():
    engine = PatchedEngine()
    class FakeProfile:
        seed = 42069
        target_os = "linux"
        timezone = "Europe/Berlin"
        locale = "de-DE"
    args = engine.build_args(FakeProfile())
    assert "--fingerprint=42069" in args
    assert "--fingerprint-platform=linux" in args
    assert "--fingerprint-timezone=Europe/Berlin" in args
    assert "--fingerprint-locale=de-DE" in args


def test_patched_engine_build_args_partial_profile():
    engine = PatchedEngine()
    class FakeProfile:
        seed = 100
        target_os = None
        timezone = None
        locale = None
    args = engine.build_args(FakeProfile())
    assert args == ["--fingerprint=100"]
