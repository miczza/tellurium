from tellurium.browser.engine import PatchedEngine, StockEngine


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
    assert "native_timezone" in caps


def test_patched_engine_build_args_no_profile_uses_random_seed():
    """The fork requires --fingerprint: with no profile/seed a random seed is used."""
    engine = PatchedEngine()
    args = engine.build_args(None)
    assert len(args) == 1 and args[0].startswith("--fingerprint=")
    assert engine.seed is not None and args[0] == f"--fingerprint={engine.seed}"


def test_patched_engine_build_args_explicit_seed_without_profile():
    engine = PatchedEngine(seed=42069)
    assert engine.build_args(None) == ["--fingerprint=42069"]


def test_patched_engine_build_args_with_profile():
    engine = PatchedEngine()

    class FakeProfile:
        seed = 42069
        target_os = "linux"
        timezone = "Europe/Berlin"
        locale = "de-DE"

    args = engine.build_args(FakeProfile())
    assert args == [
        "--fingerprint=42069",
        "--fingerprint-platform=linux",
        "--fingerprint-timezone=Europe/Berlin",
    ]
    # locale is NOT a flag of chromium-telluride (Intl and languages go via --lang and CDP)
    assert not any("locale" in a for a in args)


def test_patched_engine_build_args_partial_profile():
    engine = PatchedEngine()

    class FakeProfile:
        seed = 100
        target_os = None
        timezone = None
        locale = None

    args = engine.build_args(FakeProfile())
    assert args == ["--fingerprint=100"]
