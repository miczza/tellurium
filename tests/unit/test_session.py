import os
from pathlib import Path

import pytest

from tellurium.session import Session


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
