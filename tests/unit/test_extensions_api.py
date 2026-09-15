import pytest


def test_launch_extensions_requires_unpacked_dir(tmp_path):
    """Passing a .crx file must raise ValueError (only unpacked dirs supported)."""
    crx = tmp_path / "ext.crx"
    crx.write_bytes(b"fake-crx")
    with pytest.raises(ValueError, match="unpacked directory"):
        from tellurium.browser.launcher import validate_extension_paths

        validate_extension_paths([str(crx)])


def test_launch_extensions_requires_manifest_json(tmp_path):
    """An unpacked dir without manifest.json must raise ValueError."""
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    from tellurium.browser.launcher import validate_extension_paths

    with pytest.raises(ValueError, match="manifest.json"):
        validate_extension_paths([str(ext_dir)])


def test_launch_extensions_accepts_valid_dir(tmp_path):
    """Valid unpacked dir passes validation."""
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text('{"name":"x","version":"1","manifest_version":3}')
    from tellurium.browser.launcher import validate_extension_paths

    validate_extension_paths([str(ext_dir)])


def test_launch_chrome_branded_137_with_extensions_raises(tmp_path):
    """Chrome branded >= 137 + extensions must raise LaunchError."""
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text('{"name":"x","version":"1"}')

    from tellurium.browser.launcher import LaunchError, check_chrome_version_for_extensions

    with pytest.raises(LaunchError, match="does not support --load-extension") as exc:
        check_chrome_version_for_extensions(
            executable="/usr/bin/google-chrome",
            version=(137, 0, 0, 0),
            is_branded_chrome=True,
            extensions=[str(ext_dir)],
        )
    assert "/usr/bin/google-chrome" in str(exc.value)


def test_extensions_flag_merged_with_tellurium_stealth_ext(tmp_path):
    """In stock + stealth, --load-extension merges tellurium ext + user ext."""
    ext_dir = tmp_path / "ubo"
    ext_dir.mkdir()
    (ext_dir / "manifest.json").write_text('{"name":"ubo","version":"1"}')

    from tellurium.browser.launcher import build_load_extension_flag

    flag = build_load_extension_flag(
        tellurium_stealth_path=str(tmp_path / "tellurium-stealth"),
        user_extensions=[str(ext_dir)],
    )
    assert flag.startswith("--load-extension=")
    assert "tellurium-stealth" in flag
    assert str(ext_dir) in flag
    parts = flag.removeprefix("--load-extension=").split(",")
    assert parts[0].endswith("tellurium-stealth")
    assert parts[1] == str(ext_dir)


def test_build_load_extension_flag_empty_raises():
    """build_load_extension_flag must refuse to produce an empty flag."""
    from tellurium.browser.launcher import build_load_extension_flag

    with pytest.raises(ValueError, match="at least one path"):
        build_load_extension_flag(tellurium_stealth_path=None, user_extensions=[])
