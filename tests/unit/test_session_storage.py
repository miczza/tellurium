import json
import os
import sys

import pytest

from tellurium.session import storage


def test_save_writes_valid_json(tmp_path):
    path = tmp_path / "session.json"
    data = {"name": "mario", "seed": 42, "metadata": {"k": "v"}, "created_at": "2026-01-01T00:00:00+00:00"}
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
        "name": "x", "seed": 1, "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00",
        "launch": {"stealth": True, "proxy": "socks5://h:1", "headless": False, "args": ["--x"]},
    }
    storage.save(str(path), data, full=True)

    loaded = json.loads(path.read_text())
    assert loaded["launch"]["stealth"] is True
    assert loaded["launch"]["proxy"] == "socks5://h:1"


def test_save_lean_omits_launch_block(tmp_path):
    path = tmp_path / "session.json"
    data = {
        "name": "x", "seed": 1, "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00",
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


import warnings


def test_load_returns_none_when_missing(tmp_path):
    path = tmp_path / "nope.json"
    assert storage.load(str(path)) is None


def test_load_roundtrip(tmp_path):
    path = tmp_path / "session.json"
    original = {
        "name": "mario", "seed": 42, "metadata": {"username": "mario"},
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
        "name": "x", "seed": 1, "metadata": {}, "created_at": "2026-01-01T00:00:00+00:00",
        "launch": {"stealth": True, "headless": False},
    }
    storage.save(str(path), data, full=True)

    loaded = storage.load(str(path))
    assert loaded["launch"]["stealth"] is True


def test_load_warns_on_unknown_fields(tmp_path):
    path = tmp_path / "session.json"
    payload = {
        "tellurium_version": "0.1.0",
        "name": "x", "seed": 1, "metadata": {},
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
