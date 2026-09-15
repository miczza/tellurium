from tellurium.stealth.profile import _LCG, StealthProfile


def test_lcg_determinism():
    a = _LCG(42069)
    b = _LCG(42069)
    for _ in range(100):
        assert a.next_uint32() == b.next_uint32()


def test_lcg_different_seeds():
    a = _LCG(1)
    b = _LCG(2)
    assert a.next_uint32() != b.next_uint32()


def test_seed_determinism():
    p1 = StealthProfile.from_seed(42069)
    p2 = StealthProfile.from_seed(42069)
    assert p1 == p2


def test_different_seeds_differ():
    p1 = StealthProfile.from_seed(42069)
    p2 = StealthProfile.from_seed(42070)
    assert p1.webgl_renderer != p2.webgl_renderer or p1.screen_width != p2.screen_width


def test_windows_profile_coherence():
    p = StealthProfile.from_seed(42069, os="windows")
    assert p.platform == "Win32"
    assert p.ch_ua_platform == "Windows"
    assert "Windows NT" in p.user_agent
    assert "Direct3D11" in p.webgl_renderer


def test_macos_profile_coherence():
    p = StealthProfile.from_seed(42069, os="macos")
    assert p.platform == "MacIntel"
    assert p.ch_ua_platform == "macOS"
    assert "Metal" in p.webgl_renderer
    assert p.device_pixel_ratio == 2.0


def test_linux_profile_coherence():
    p = StealthProfile.from_seed(42069, os="linux")
    assert p.platform == "Linux x86_64"
    assert p.ch_ua_platform == "Linux"
    assert "OpenGL" in p.webgl_renderer or "Vulkan" in p.webgl_renderer


def test_client_hints_match_ua():
    p = StealthProfile.from_seed(42069)
    major = p.browser_version.split(".")[0]
    assert f'v="{major}"' in p.ch_ua


def test_auto_generates_valid_profile():
    p = StealthProfile.auto()
    assert p.seed > 0
    assert p.user_agent
    assert p.webgl_vendor
    assert p.screen_width > 0


def test_hardware_concurrency_reasonable():
    p = StealthProfile.from_seed(42069)
    assert p.hardware_concurrency in [4, 8, 12, 16]


def test_device_memory_reasonable():
    p = StealthProfile.from_seed(42069)
    assert p.device_memory in [4, 8, 16]
