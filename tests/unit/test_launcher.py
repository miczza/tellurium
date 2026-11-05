from unittest.mock import patch

from tellurium.browser.launcher import (
    _determine_platform,
    build_chrome_flags,
)


def test_determine_platform_linux():
    with patch("sys.platform", "linux"), patch("platform.machine", return_value="x86_64"):
        assert _determine_platform() == "linux64"


def test_build_chrome_flags_base():
    flags = build_chrome_flags(
        headless=False, user_data_dir="/tmp/td", proxy=None, extra_args=None, engine_args=[]
    )
    assert "--remote-debugging-pipe" in flags
    assert "--no-first-run" in flags
    assert "--user-data-dir=/tmp/td" in flags
    assert "--headless=new" not in flags


def test_build_chrome_flags_headless():
    flags = build_chrome_flags(
        headless=True, user_data_dir="/tmp/td", proxy=None, extra_args=None, engine_args=[]
    )
    assert "--headless=new" in flags


def test_build_chrome_flags_proxy():
    flags = build_chrome_flags(
        headless=False,
        user_data_dir="/tmp/td",
        proxy="localhost:8080",
        extra_args=None,
        engine_args=[],
    )
    assert "--proxy-server=localhost:8080" in flags


def test_build_chrome_flags_extra():
    flags = build_chrome_flags(
        headless=False,
        user_data_dir="/tmp/td",
        proxy=None,
        extra_args=["--disable-gpu"],
        engine_args=["--fingerprint=42"],
    )
    assert "--disable-gpu" in flags
    assert "--fingerprint=42" in flags
