"""The 500-line ceiling on every module of tellurium/: the files already past it
(listed with their size when the rule came) may only shrink, and those that
reached it were split below 450 lines. The generated CDP domains are exempt."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPLIT = 450
CEILING = 500
#: Past the ceiling before it applied: they never grow (lower these as they shrink).
OVER = {
    "tellurium/browser/tab.py": 1109,
    "tellurium/browser/launcher.py": 671,
    "tellurium/browser/browser.py": 560,
    "tellurium/cdp/generator.py": 503,
}
GENERATED = "tellurium/cdp/domains/"


def _modules() -> list[str]:
    return sorted(
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "tellurium").rglob("*.py")
        if not p.relative_to(ROOT).as_posix().startswith(GENERATED)
    )


def _lines(path: str) -> int:
    return (ROOT / path).read_text(encoding="utf-8").count("\n")


def test_every_module_is_under_the_ceiling_or_does_not_grow():
    too_long = {
        path: lines for path in _modules() if (lines := _lines(path)) > OVER.get(path, CEILING)
    }
    assert not too_long, f"over {CEILING} lines (or grown past their old size): {too_long}"


def test_the_list_of_files_past_the_ceiling_is_current():
    for path in OVER:
        assert (ROOT / path).is_file(), f"{path} is gone: drop it from OVER"


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
    assert snapshot.AXTree is snapshot_text.AXTree
    assert snapshot.build_nodes is snapshot_text.build_nodes
    assert snapshot.render is snapshot_text.render
