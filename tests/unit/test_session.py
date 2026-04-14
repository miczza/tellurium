import os
from pathlib import Path

import pytest

from tellurium.session import Session
from tellurium.session import SessionCorruptError
from tellurium.session import storage as _storage


def test_constructs_with_name_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Session("mario")
    assert s.name == "mario"
    # default path is ./sessions/{name}
    assert s.path == os.path.abspath(os.path.join("sessions", "mario"))


def test_uses_explicit_path(tmp_path):
    s = Session("mario", path=str(tmp_path / "custom"))
    assert s.path == str(tmp_path / "custom")


def test_seed_from_constructor(tmp_path):
    s = Session("x", path=str(tmp_path / "s"), seed=42069)
    assert s.seed == 42069


def test_seed_random_when_none(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    assert isinstance(s.seed, int)
    assert s.seed > 0


def test_metadata_empty_initially(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    assert s.metadata == {}


def test_validate_mode_default_all(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    assert s.validate_mode == "all"


def test_validate_mode_any(tmp_path):
    s = Session("x", path=str(tmp_path / "s"), validate_mode="any")
    assert s.validate_mode == "any"


def test_validate_mode_invalid_raises(tmp_path):
    with pytest.raises(ValueError):
        Session("x", path=str(tmp_path / "s"), validate_mode="maybe")


def _write_session_file(dir_path: Path, data: dict) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    _storage.save(str(dir_path / "session.json"), data, full=("launch" in data))


def test_loads_metadata_and_seed_from_file(tmp_path):
    path = tmp_path / "s"
    _write_session_file(path, {
        "name": "mario", "seed": 7777, "metadata": {"username": "mario"},
        "created_at": "2026-01-01T00:00:00+00:00",
    })

    s = Session("mario", path=str(path))
    assert s.seed == 7777
    assert s.metadata == {"username": "mario"}


def test_constructor_seed_ignored_when_file_exists(tmp_path):
    path = tmp_path / "s"
    _write_session_file(path, {
        "name": "mario", "seed": 7777, "metadata": {},
        "created_at": "2026-01-01T00:00:00+00:00",
    })

    s = Session("mario", path=str(path), seed=9999)
    assert s.seed == 7777


def test_loads_launch_hints_when_present(tmp_path):
    path = tmp_path / "s"
    _write_session_file(path, {
        "name": "x", "seed": 1, "metadata": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "launch": {"stealth": True, "headless": False},
    })

    s = Session("x", path=str(path))
    assert s._launch_hints == {"stealth": True, "headless": False}


def test_corrupt_file_raises(tmp_path):
    path = tmp_path / "s"
    path.mkdir()
    (path / "session.json").write_text("{garbage")

    with pytest.raises(SessionCorruptError):
        Session("x", path=str(path))


def test_add_sets_if_missing(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    s.add("username", "mario")
    assert s.metadata["username"] == "mario"


def test_add_noop_if_present(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    s.add("username", "mario")
    s.add("username", "NEW")
    assert s.metadata["username"] == "mario"


def test_set_overwrites_unconditionally(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    s.set("username", "mario")
    s.set("username", "NEW")
    assert s.metadata["username"] == "NEW"


def test_get_returns_none_by_default(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    assert s.get("missing") is None


def test_get_explicit_default(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    assert s.get("missing", default="fallback") == "fallback"


def test_get_returns_value(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    s.set("k", "v")
    assert s.get("k") == "v"


def test_add_rejects_non_json_value(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    with pytest.raises(TypeError):
        s.add("f", lambda: None)


def test_set_rejects_non_json_value(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    with pytest.raises(TypeError):
        s.set("f", object())


def test_set_accepts_nested_container(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    s.set("nested", {"a": [1, 2, {"b": None, "c": True}]})
    assert s.metadata["nested"]["a"][2]["c"] is True


def test_set_rejects_nan_and_infinity(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    with pytest.raises(TypeError):
        s.set("bad", float("nan"))
    with pytest.raises(TypeError):
        s.set("bad", float("inf"))
    with pytest.raises(TypeError):
        s.set("bad", float("-inf"))
