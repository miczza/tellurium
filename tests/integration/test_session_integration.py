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


async def test_first_run_triggers_login_then_persists(tmp_path, local_server):
    s = Session("login-test", path=str(tmp_path / "s"))
    s.add("username", "mario")
    s.add("password", "secret")

    @s.validate
    async def signed_in(tab):
        await tab.get(f"{local_server}/dashboard.html")
        # A visible .welcome element means logged in
        el = await tab.select(".welcome", timeout=2)
        return el is not None

    @s.login
    async def do_login(tab, metadata):
        await tab.get(f"{local_server}/login.html")
        user_field = await tab.select("#user")
        await user_field.type(metadata["username"])
        pass_field = await tab.select("#pass")
        await pass_field.type(metadata["password"])
        submit = await tab.select("#submit")
        await submit.click()
        # Give the JS a moment to set the cookie
        await tab.wait(0.6)

    # First run: no cookie exists, validator fails, login runs
    async with s.start(headless=True) as browser:
        # After login, navigate to dashboard and check visible
        tab = browser.main_tab
        await tab.get(f"{local_server}/dashboard.html")
        el = await tab.select(".welcome", timeout=3)
        assert el is not None
        s.save()

    # session.json must exist and contain our metadata
    import os, json as J
    assert os.path.exists(os.path.join(s.path, "session.json"))
    data = J.loads(open(os.path.join(s.path, "session.json")).read())
    assert data["metadata"]["username"] == "mario"


async def test_second_run_skips_login(tmp_path, local_server):
    # Pre-populate a session by running the first-run scenario inline
    s = Session("skip-test", path=str(tmp_path / "s"))
    s.add("username", "mario")
    s.add("password", "secret")

    login_calls = {"n": 0}

    @s.validate
    async def signed_in(tab):
        await tab.get(f"{local_server}/dashboard.html")
        el = await tab.select(".welcome", timeout=2)
        return el is not None

    @s.login
    async def do_login(tab, metadata):
        login_calls["n"] += 1
        await tab.get(f"{local_server}/login.html")
        await (await tab.select("#user")).type(metadata["username"])
        await (await tab.select("#pass")).type(metadata["password"])
        await (await tab.select("#submit")).click()
        await tab.wait(0.6)

    async with s.start(headless=True):
        s.save()
    assert login_calls["n"] == 1

    # Re-open the same session dir: cookie is still in user_data_dir
    s2 = Session("skip-test", path=str(tmp_path / "s"))
    validator_calls = {"n": 0}
    login_calls2 = {"n": 0}

    @s2.validate
    async def signed_in2(tab):
        validator_calls["n"] += 1
        await tab.get(f"{local_server}/dashboard.html")
        el = await tab.select(".welcome", timeout=2)
        return el is not None

    @s2.login
    async def do_login2(tab, metadata):
        login_calls2["n"] += 1

    async with s2.start(headless=True):
        pass

    assert validator_calls["n"] == 1
    assert login_calls2["n"] == 0
