import pytest

from tellurium.session import Session, SessionInvalidError, SessionLoginFailedError
from tests.timeout_scale import scaled


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

    async with s.start(headless=True):
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
        async with s.start(headless=True, user_data_dir=str(tmp_path / "x")):
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
        el = await tab.select(".welcome", timeout=scaled(3))
        assert el is not None
        await s.save_now()

    # session.json must exist and contain our metadata
    import json as J
    import os

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
        await s.save_now()
    assert login_calls["n"] == 1

    # Re-open the same session dir: cookie is still in user_data_dir
    s2 = Session("skip-test", path=str(tmp_path / "s"))
    validator_calls = {"n": 0}
    login_calls2 = {"n": 0}

    @s2.validate
    async def signed_in2(tab):
        validator_calls["n"] += 1
        await tab.get(f"{local_server}/dashboard.html")
        el = await tab.select(".welcome", timeout=scaled(2))
        return el is not None

    @s2.login
    async def do_login2(tab, metadata):
        login_calls2["n"] += 1

    async with s2.start(headless=True):
        pass

    assert validator_calls["n"] == 1
    assert login_calls2["n"] == 0


async def test_portability_new_session_loads_metadata(tmp_path, local_server):
    # Step 1: script A saves a session with credentials
    s_a = Session("port-test", path=str(tmp_path / "s"))
    s_a.add("username", "luigi")
    s_a.add("password", "shhh")

    @s_a.validate
    async def _v(tab):
        await tab.get(f"{local_server}/dashboard.html")
        return (await tab.select(".welcome", timeout=2)) is not None

    @s_a.login
    async def _l(tab, metadata):
        await tab.get(f"{local_server}/login.html")
        await (await tab.select("#user")).type(metadata["username"])
        await (await tab.select("#pass")).type(metadata["password"])
        await (await tab.select("#submit")).click()
        await tab.wait(0.6)

    async with s_a.start(headless=True):
        await s_a.save_now()

    # Step 2: script B constructs a Session with just the name/path, no
    # hardcoded credentials. Simulate cookie invalidation by deleting cookies
    # dir from user_data_dir, and the session's own cookies.json, so the
    # validator will fail.
    import os
    import shutil

    os.remove(os.path.join(s_a.path, "cookies.json"))
    # Chrome keeps them in Default/ or, as on Windows, in Default/Network/.
    removed = 0
    for folder in ("Default", os.path.join("Default", "Network")):
        default_dir = os.path.join(s_a.path, "chrome", folder)
        if not os.path.isdir(default_dir):
            continue
        for entry in os.listdir(default_dir):
            if entry.startswith("Cookies"):
                target = os.path.join(default_dir, entry)
                if os.path.isdir(target):
                    shutil.rmtree(target)
                else:
                    os.remove(target)
                removed += 1
    assert removed  # else the validator passes on the old cookies

    s_b = Session("port-test", path=str(tmp_path / "s"))
    # script B never calls .add() -- relies entirely on file contents
    assert s_b.metadata.get("username") == "luigi"
    assert s_b.metadata.get("password") == "shhh"

    login_called = {"n": 0}

    @s_b.validate
    async def _v2(tab):
        await tab.get(f"{local_server}/dashboard.html")
        return (await tab.select(".welcome", timeout=2)) is not None

    @s_b.login
    async def _l2(tab, metadata):
        login_called["n"] += 1
        await tab.get(f"{local_server}/login.html")
        await (await tab.select("#user")).type(metadata["username"])
        await (await tab.select("#pass")).type(metadata["password"])
        await (await tab.select("#submit")).click()
        await tab.wait(0.6)

    async with s_b.start(headless=True) as browser:
        tab = browser.main_tab
        await tab.get(f"{local_server}/dashboard.html")
        assert (await tab.select(".welcome", timeout=scaled(3))) is not None

    assert login_called["n"] == 1


async def test_validation_fails_no_login_raises(tmp_path, local_server):
    s = Session("err1", path=str(tmp_path / "s"))

    @s.validate
    async def never(tab):
        return False

    with pytest.raises(SessionInvalidError):
        async with s.start(headless=True):
            pass


async def test_login_raising_wraps_in_login_failed(tmp_path, local_server):
    s = Session("err2", path=str(tmp_path / "s"))

    @s.validate
    async def never(tab):
        return False

    @s.login
    async def bad(tab, metadata):
        raise ValueError("simulated failure")

    with pytest.raises(SessionLoginFailedError) as ei:
        async with s.start(headless=True):
            pass
    assert isinstance(ei.value.__cause__, ValueError)
    assert "simulated failure" in str(ei.value.__cause__)


async def test_validation_passes_any_mode(tmp_path, local_server):
    s = Session("any1", path=str(tmp_path / "s"), validate_mode="any")

    @s.validate
    async def falsy(tab):
        return False

    @s.validate
    async def truthy(tab):
        return True

    @s.login
    async def should_not_run(tab, metadata):
        raise AssertionError("login should not run when any validator passes")

    async with s.start(headless=True):
        pass


async def test_no_validators_launches_without_checks(tmp_path, local_server):
    s = Session("novalid", path=str(tmp_path / "s"))
    # No @validate, no @login — should still work

    async with s.start(headless=True) as browser:
        assert browser is not None


async def test_full_save_roundtrips_launch_params(tmp_path, local_server):
    s = Session("full1", path=str(tmp_path / "s"))

    async with s.start(headless=True):
        await s.save_now(full=True)

    # Reopen the same session: launch_hints should now contain headless=True
    s2 = Session("full1", path=str(tmp_path / "s"))
    assert s2._launch_hints.get("headless") is True


async def test_a_too_nested_cookies_file_warns_and_the_start_goes_on(tmp_path):
    """100 000 ``[`` (a RecursionError while parsing): a warning, the file set
    aside, and the close writes a good one."""
    import json

    path = tmp_path / "s"
    path.mkdir()
    (path / "cookies.json").write_text("[" * 100_000)
    with pytest.warns(UserWarning, match="cookies.json"):
        async with Session("s", path=str(path)).start(headless=True) as browser:
            assert await browser.main_tab.eval("1 + 1") == 2
    assert json.loads((path / "cookies.json").read_text())["at_close"] is True
    assert any(p.name.startswith("cookies.json.bad-") for p in path.iterdir())


async def test_save_now_writes_the_cookie_chrome_has_now(tmp_path, local_server):
    """A cookie set by the page a moment ago is in cookies.json while Chrome
    still runs; save() on the loop points to save_now instead."""
    import json

    session = Session("s", path=str(tmp_path / "s"))
    async with session.start(headless=True) as browser:
        tab = browser.main_tab
        await tab.get(f"{local_server}/basic.html")
        await tab.eval("document.cookie = 'fresh=1; path=/'")
        await session.save_now()
        saved = json.loads((tmp_path / "s" / "cookies.json").read_text())
        assert any(c["name"] == "fresh" and c["expires"] == -1 for c in saved["cookies"])
        assert saved["at_close"] is False
        assert (tmp_path / "s" / "session.json").exists()
        with pytest.raises(RuntimeError, match="save_now"):
            session.save()
