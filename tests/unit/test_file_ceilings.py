"""The files that reached the 500-line ceiling were split below 450 lines."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPLIT = 450


@pytest.mark.parametrize(
    "path",
    [
        "tellurium/browser/robots.py",
        "tellurium/browser/snapshot.py",
        "tellurium/stealth/scripts/trap_link.js",
    ],
)
def test_split_file_is_under_the_ceiling(path):
    lines = (ROOT / path).read_text(encoding="utf-8").count("\n")
    assert lines <= SPLIT, f"{path}: {lines} lines"


def test_the_robots_parser_lives_in_its_own_module():
    from tellurium.browser import robots, robots_rules

    assert robots.parse is robots_rules.parse
    assert robots.RobotsRules is robots_rules.RobotsRules
    assert robots.ALLOW_ALL is robots_rules.ALLOW_ALL
    assert robots.DISALLOW_ALL is robots_rules.DISALLOW_ALL


def test_the_snapshot_text_lives_in_its_own_module():
    from tellurium.browser import snapshot, snapshot_text

    assert snapshot.SnapshotNode is snapshot_text.SnapshotNode
    assert snapshot.build_nodes is snapshot_text.build_nodes
    assert snapshot.render is snapshot_text.render
