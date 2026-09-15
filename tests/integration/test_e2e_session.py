"""End-to-end tests for Session persistence."""

from tellurium.session import Session


async def test_session_create_and_save(tmp_path, local_server):
    """Session creates directory structure and saves metadata."""
    session_path = tmp_path / "sessions"
    session = Session("test_user", path=str(session_path), seed=12345)
    session.add("username", "testuser")
    session.add("token", "abc123")

    # Verify metadata stored
    assert session.get("username") == "testuser"
    assert session.get("token") == "abc123"

    # Verify seed is set
    assert session.seed == 12345

    # Save and verify file created
    session.save()
    session_file = session_path / "session.json"
    assert session_file.exists()


async def test_session_restore_metadata(tmp_path):
    """Session restores metadata from saved file."""
    session_path = tmp_path / "sessions"

    # Create and save
    s1 = Session("restore_test", path=str(session_path), seed=99999)
    s1.add("key1", "value1")
    s1.save()

    # Load in new Session instance
    s2 = Session("restore_test", path=str(session_path))
    assert s2.get("key1") == "value1"
    # Seed from file takes precedence
    assert s2.seed == 99999


async def test_session_with_browser(tmp_path, local_server):
    """Session.start() launches browser and runs validators."""
    session_path = tmp_path / "sessions"
    session = Session("browser_test", path=str(session_path), seed=42069)

    validation_ran = False

    @session.validate
    async def check_page(tab):
        nonlocal validation_ran
        validation_ran = True
        # Just return True to pass validation
        return True

    async with session.start(headless=True) as browser:
        assert browser is not None
        assert len(browser.tabs) >= 1

    assert validation_ran


async def test_session_login_flow(tmp_path, local_server):
    """Session calls login callback when validation fails."""
    session_path = tmp_path / "sessions"
    session = Session("login_test", path=str(session_path))
    session.add("username", "testuser")

    login_called = False

    @session.validate
    async def always_fail(tab):
        return False

    @session.login
    async def do_login(tab, metadata):
        nonlocal login_called
        login_called = True
        assert metadata["username"] == "testuser"
        # Navigate to simulate login
        await tab.get(f"{local_server}/basic.html")

    async with session.start(headless=True):
        pass

    assert login_called
