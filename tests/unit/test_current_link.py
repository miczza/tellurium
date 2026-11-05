"""The cache's ``current`` link switches even where a directory link cannot
be replaced in one rename (Windows: ``MoveFileEx`` refuses a directory
destination with ``ERROR_ACCESS_DENIED``)."""

from __future__ import annotations

import os

import pytest

from tellurium.browser import _cache

OLD, NEW = "146.0.7680.188", "147.0.7700.10"


def _refuse_directory_destinations(monkeypatch, fail_on: int | None = None):
    """``os.replace`` as on Windows; the *fail_on*-th call fails anyway."""
    real = os.replace
    calls = []

    def replace(src, dst):
        calls.append((src, dst))
        if fail_on is not None and len(calls) == fail_on:
            raise OSError(5, "simulated failure")
        if os.path.islink(dst) and os.path.isdir(dst):
            raise PermissionError(13, "Access is denied")
        return real(src, dst)

    monkeypatch.setattr(_cache.os, "replace", replace)
    return calls


@pytest.fixture
def root(tmp_path):
    for v in (OLD, NEW):
        (tmp_path / v).mkdir()
    _cache.set_current(OLD, tmp_path)
    return tmp_path


def _leftovers(root):
    return sorted(p.name for p in root.iterdir() if p.name.startswith(f".{_cache.CURRENT_LINK}"))


def test_current_switches_where_a_directory_link_cannot_be_replaced(root, monkeypatch):
    _refuse_directory_destinations(monkeypatch)
    _cache.set_current(NEW, root)
    assert _cache.current_version(root) == NEW
    _cache.set_current(OLD, root)
    assert _cache.current_version(root) == OLD
    assert _leftovers(root) == []


def test_a_failed_switch_keeps_the_old_current(root, monkeypatch):
    _refuse_directory_destinations(monkeypatch, fail_on=3)  # the new link moving in
    with pytest.raises(OSError, match="simulated"):
        _cache.set_current(NEW, root)
    assert _cache.current_version(root) == OLD
    assert _leftovers(root) == []
