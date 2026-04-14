import pytest

from tellurium import Browser
from tellurium.session import Session


async def test_start_launches_and_closes(tmp_path):
    s = Session("t1", path=str(tmp_path / "s"))

    async with s.start(headless=True) as browser:
        assert browser is not None
        assert len(browser.tabs) >= 1

    # After exit, a second start should work (fresh launch)
    async with s.start(headless=True) as browser:
        assert browser is not None


async def test_start_uses_session_user_data_dir(tmp_path):
    import os
    s = Session("t2", path=str(tmp_path / "s"))

    async with s.start(headless=True) as browser:
        expected = os.path.join(s.path, "chrome")
        assert os.path.isdir(expected)


async def test_double_start_raises(tmp_path):
    s = Session("t3", path=str(tmp_path / "s"))

    async with s.start(headless=True):
        with pytest.raises(RuntimeError):
            async with s.start(headless=True):
                pass


async def test_start_rejects_user_data_dir_kwarg(tmp_path):
    s = Session("t4", path=str(tmp_path / "s"))
    with pytest.raises(TypeError):
        async with s.start(headless=True, user_data_dir="/tmp/x"):
            pass


async def test_start_rejects_seed_kwarg(tmp_path):
    s = Session("t5", path=str(tmp_path / "s"))
    with pytest.raises(TypeError):
        async with s.start(headless=True, seed=123):
            pass
