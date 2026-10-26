import json as _json
import os
from pathlib import Path

import pytest

from tellurium.session import Session, SessionCorruptError
from tellurium.session import storage as _storage
from tellurium.session.session import _combine_validators, _merge_launch_params


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
    _write_session_file(
        path,
        {
            "name": "mario",
            "seed": 7777,
            "metadata": {"username": "mario"},
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )

    s = Session("mario", path=str(path))
    assert s.seed == 7777
    assert s.metadata == {"username": "mario"}


def test_constructor_seed_ignored_when_file_exists(tmp_path):
    path = tmp_path / "s"
    _write_session_file(
        path,
        {
            "name": "mario",
            "seed": 7777,
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
        },
    )

    s = Session("mario", path=str(path), seed=9999)
    assert s.seed == 7777


def test_loads_launch_hints_when_present(tmp_path):
    path = tmp_path / "s"
    _write_session_file(
        path,
        {
            "name": "x",
            "seed": 1,
            "metadata": {},
            "created_at": "2026-01-01T00:00:00+00:00",
            "launch": {"stealth": True, "headless": False},
        },
    )

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


def test_validate_registers_callback(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))

    @s.validate
    async def v(tab):
        return True

    assert v in s._validators
    assert len(s._validators) == 1


def test_multiple_validates_all_registered(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))

    @s.validate
    async def a(tab):
        return True

    @s.validate
    async def b(tab):
        return True

    assert s._validators == [a, b]


def test_login_registers_callback(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))

    @s.login
    async def do(tab, metadata):
        pass

    assert s._login is do


def test_second_login_replaces_with_warning(tmp_path, recwarn):
    s = Session("x", path=str(tmp_path / "s"))

    @s.login
    async def a(tab, metadata):
        pass

    @s.login
    async def b(tab, metadata):
        pass

    assert s._login is b
    assert any("login" in str(w.message).lower() for w in recwarn.list)


async def _always_true(tab):
    return True


async def _always_false(tab):
    return False


async def _raises(tab):
    raise RuntimeError("boom")


async def test_combine_all_all_true():
    result = await _combine_validators([_always_true, _always_true], "all", tab=None)
    assert result is True


async def test_combine_all_short_circuits_on_first_false():
    calls = []

    async def a(tab):
        calls.append("a")
        return False

    async def b(tab):
        calls.append("b")
        return True

    result = await _combine_validators([a, b], "all", tab=None)
    assert result is False
    assert calls == ["a"]


async def test_combine_all_treats_raise_as_false():
    result = await _combine_validators([_raises, _always_true], "all", tab=None)
    assert result is False


async def test_combine_any_short_circuits_on_first_true():
    calls = []

    async def a(tab):
        calls.append("a")
        return True

    async def b(tab):
        calls.append("b")
        return True

    result = await _combine_validators([a, b], "any", tab=None)
    assert result is True
    assert calls == ["a"]


async def test_combine_any_skips_raising_validators():
    result = await _combine_validators([_raises, _always_true], "any", tab=None)
    assert result is True


async def test_combine_any_all_false_is_false():
    result = await _combine_validators([_always_false, _always_false], "any", tab=None)
    assert result is False


async def test_combine_any_all_raise_is_false():
    result = await _combine_validators([_raises, _raises], "any", tab=None)
    assert result is False


def test_merge_kwargs_win_over_hints():
    merged = _merge_launch_params({"stealth": True}, {"stealth": False, "headless": True})
    assert merged == {"stealth": True, "headless": True}


def test_merge_hints_used_when_no_kwargs():
    merged = _merge_launch_params({}, {"stealth": True, "proxy": "p"})
    assert merged == {"stealth": True, "proxy": "p"}


def test_merge_kwargs_used_when_no_hints():
    merged = _merge_launch_params({"headless": True}, {})
    assert merged == {"headless": True}


def test_merge_rejects_user_data_dir():
    with pytest.raises(TypeError):
        _merge_launch_params({"user_data_dir": "/tmp"}, {})


def test_merge_rejects_seed():
    with pytest.raises(TypeError):
        _merge_launch_params({"seed": 42}, {})


def test_merge_ignores_managed_keys_in_hints():
    # If somehow hints contain managed keys, they are dropped silently
    merged = _merge_launch_params({"stealth": True}, {"user_data_dir": "/x", "seed": 1})
    assert "user_data_dir" not in merged
    assert "seed" not in merged
    assert merged["stealth"] is True


def test_save_lean_writes_metadata_and_seed(tmp_path):
    s = Session("mario", path=str(tmp_path / "s"), seed=42)
    s.add("username", "mario")
    s.save()

    data = _json.loads((tmp_path / "s" / "session.json").read_text())
    assert data["name"] == "mario"
    assert data["seed"] == 42
    assert data["metadata"] == {"username": "mario"}
    assert "launch" not in data


def test_save_full_without_launch_info_is_lean(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    s.save(full=True)  # nothing captured from start() yet

    data = _json.loads((tmp_path / "s" / "session.json").read_text())
    assert "launch" not in data


def test_save_preserves_created_at_on_update(tmp_path):
    # First save -> sets created_at. Second save on the same session keeps it.
    s = Session("x", path=str(tmp_path / "s"))
    s.save()
    first = _json.loads((tmp_path / "s" / "session.json").read_text())["created_at"]

    # Mutate and save again via a fresh Session (simulates a later run)
    s2 = Session("x", path=str(tmp_path / "s"))
    s2.set("k", "v")
    s2.save()
    second = _json.loads((tmp_path / "s" / "session.json").read_text())["created_at"]

    assert first == second


def test_save_full_with_last_launch_params(tmp_path):
    s = Session("x", path=str(tmp_path / "s"))
    s._last_launch_params = {"stealth": True, "headless": False}
    s.save(full=True)

    data = _json.loads((tmp_path / "s" / "session.json").read_text())
    assert data["launch"] == {"stealth": True, "headless": False}


def test_fresh_seed_ignores_the_global_random_state(tmp_path):
    # A script that calls random.seed() must not hand every new identity one fingerprint.
    import random

    random.seed(42)
    a = Session("a", path=str(tmp_path / "a")).seed
    random.seed(42)
    b = Session("b", path=str(tmp_path / "b")).seed
    assert a != b


def test_session_pool_is_exported_from_tellurium():
    import tellurium
    from tellurium.session import SessionPool

    assert tellurium.SessionPool is SessionPool
    assert "SessionPool" in tellurium.__all__
