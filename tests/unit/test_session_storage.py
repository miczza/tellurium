import json
import sys
import warnings

import pytest

from tellurium.session import storage


def test_save_writes_valid_json(tmp_path):
    path = tmp_path / "session.json"
    data = {
        "name": "mario",
        "seed": 42,
        "metadata": {"k": "v"},
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    storage.save(str(path), data, full=False)

    loaded = json.loads(path.read_text())
    assert loaded["name"] == "mario"
    assert loaded["seed"] == 42
    assert loaded["metadata"] == {"k": "v"}


def test_save_sets_updated_at(tmp_path):
    path = tmp_path / "session.json"
    data = {"name": "x", "seed": 1, "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00"}
    storage.save(str(path), data, full=False)

    loaded = json.loads(path.read_text())
    assert "updated_at" in loaded
    # ISO 8601 format with timezone
    assert "T" in loaded["updated_at"]
    assert loaded["updated_at"].endswith("+00:00") or loaded["updated_at"].endswith("Z")


def test_save_full_includes_launch_block(tmp_path):
    path = tmp_path / "session.json"
    data = {
        "name": "x",
        "seed": 1,
        "metadata": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "launch": {"stealth": True, "proxy": "socks5://h:1", "headless": False, "args": ["--x"]},
    }
    storage.save(str(path), data, full=True)

    loaded = json.loads(path.read_text())
    assert loaded["launch"]["stealth"] is True
    assert loaded["launch"]["proxy"] == "socks5://h:1"


def test_save_lean_omits_launch_block(tmp_path):
    path = tmp_path / "session.json"
    data = {
        "name": "x",
        "seed": 1,
        "metadata": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "launch": {"stealth": True},
    }
    storage.save(str(path), data, full=False)

    loaded = json.loads(path.read_text())
    assert "launch" not in loaded


def test_save_is_atomic_no_tmp_leftover(tmp_path):
    path = tmp_path / "session.json"
    data = {"name": "x", "seed": 1, "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00"}
    storage.save(str(path), data, full=False)

    # No .tmp sibling should remain
    assert not (tmp_path / "session.json.tmp").exists()
    assert path.exists()


def test_save_sets_tellurium_version(tmp_path):
    path = tmp_path / "session.json"
    data = {"name": "x", "seed": 1, "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00"}
    storage.save(str(path), data, full=False)

    loaded = json.loads(path.read_text())
    assert "tellurium_version" in loaded
    assert isinstance(loaded["tellurium_version"], str)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_save_sets_0600_permissions(tmp_path):
    path = tmp_path / "session.json"
    data = {"name": "x", "seed": 1, "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00"}
    storage.save(str(path), data, full=False)

    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_save_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "deep" / "session.json"
    data = {"name": "x", "seed": 1, "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00"}
    storage.save(str(path), data, full=False)

    assert path.exists()


def test_load_returns_none_when_missing(tmp_path):
    path = tmp_path / "nope.json"
    assert storage.load(str(path)) is None


def test_load_roundtrip(tmp_path):
    path = tmp_path / "session.json"
    original = {
        "name": "mario",
        "seed": 42,
        "metadata": {"username": "mario"},
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    storage.save(str(path), original, full=False)

    loaded = storage.load(str(path))
    assert loaded["name"] == "mario"
    assert loaded["seed"] == 42
    assert loaded["metadata"] == {"username": "mario"}


def test_load_malformed_raises_corrupt(tmp_path):
    path = tmp_path / "session.json"
    path.write_text("{not valid json")

    with pytest.raises(storage.SessionCorruptError):
        storage.load(str(path))


def test_load_full_returns_launch_block(tmp_path):
    path = tmp_path / "session.json"
    data = {
        "name": "x",
        "seed": 1,
        "metadata": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "launch": {"stealth": True, "headless": False},
    }
    storage.save(str(path), data, full=True)

    loaded = storage.load(str(path))
    assert loaded["launch"]["stealth"] is True


def test_load_warns_on_unknown_fields(tmp_path):
    path = tmp_path / "session.json"
    payload = {
        "tellurium_version": "0.1.0",
        "name": "x",
        "seed": 1,
        "metadata": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "future_field_xyz": "hello",
    }
    path.write_text(json.dumps(payload))

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        loaded = storage.load(str(path))
    assert "future_field_xyz" not in loaded
    assert any("future_field_xyz" in str(x.message) for x in w)


def test_load_rejects_non_object_root(tmp_path):
    path = tmp_path / "session.json"
    path.write_text('["not", "an", "object"]')

    with pytest.raises(storage.SessionCorruptError):
        storage.load(str(path))


def test_save_persists_chromium_version(tmp_path, monkeypatch):
    """session.save() after a launch records the chromium_version."""
    from tellurium import Session

    sess = Session("test", path=str(tmp_path / "sessions"))
    # Simulate that a launch was performed with version 146.0.7680.188
    sess._chromium_version_used = (
        "146.0.7680.188"  # internal attr set by Browser.launch/Session.start
    )
    sess.save()

    import json

    data = json.loads((tmp_path / "sessions" / "session.json").read_text())
    assert data.get("chromium_version") == "146.0.7680.188"


def test_load_restores_chromium_version_lock(tmp_path):
    """Session loaded from disk exposes chromium_version property."""
    import json

    from tellurium import Session

    sess_dir = tmp_path / "sessions"
    sess_dir.mkdir(parents=True)
    (sess_dir / "session.json").write_text(
        json.dumps(
            {
                "name": "test",
                "seed": 42069,
                "chromium_version": "146.0.7680.188",
                "created_at": "2026-04-15T10:30:00Z",
                "metadata": {},
            }
        )
    )
    sess = Session("test", path=str(sess_dir))
    assert sess.chromium_version == "146.0.7680.188"


def test_two_writers_never_leave_a_corrupt_or_partial_file(tmp_path):
    """Each write has its own temporary file: concurrent writers (a live save
    in a thread, the close) never mix their bytes or rename each other's."""
    import os
    import threading

    path = str(tmp_path / "cookies.json")
    storage.write_private(path, {"n": -1})
    errors: list[BaseException] = []
    bad: list[str] = []
    stop = threading.Event()

    def writer(k):
        try:
            for i in range(300):
                storage.write_private(path, {"n": i, "who": k, "pad": "x" * (k * 500)})
        except BaseException as exc:  # noqa: BLE001 - collected for the assert
            errors.append(exc)

    def reader():
        while not stop.is_set():
            text = storage.read_text(path)  # on Windows, retried across a rename
            try:
                json.loads(text)
            except ValueError:
                bad.append(text[:40])

    threads = [threading.Thread(target=writer, args=(k,)) for k in (1, 2)]
    watcher = threading.Thread(target=reader)
    watcher.start()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    watcher.join()
    assert errors == []
    assert bad == []
    assert os.listdir(tmp_path) == ["cookies.json"]  # no temporary file left
    if sys.platform != "win32":
        assert os.stat(path).st_mode & 0o777 == 0o600
