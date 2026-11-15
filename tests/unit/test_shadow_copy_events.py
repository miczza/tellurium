"""The shadow copy events of the hang probe, read with ``wevtutil``: a runner
frozen ~60 s timed PowerShell out and left none (run 43496669198)."""

from __future__ import annotations

import sys

import pytest

from tests import shadow_copy_events

_XML = (
    "<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>"
    "<Provider Name='VSS'/><EventID Qualifiers='0'>8224</EventID><Level>4</Level>"
    "<TimeCreated SystemTime='2026-11-13T10:00:01.5000000Z'/><Channel>Application</Channel>"
    "</System><EventData><Data>The VSS service is shutting down due to idle timeout.</Data>"
    "<Binary>2D20436F64653A</Binary></EventData></Event>"
    "<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>"
    "<Provider Name='volsnap' Guid='{x}'/><EventID>25</EventID><Level>3</Level>"
    "<TimeCreated SystemTime='2026-11-13T10:00:00.250Z'/><Channel>System</Channel>"
    "</System><EventData><Data Name='DeviceName'>\\Device\\HarddiskVolumeShadowCopy1</Data>"
    "</EventData></Event>"
)


def test_each_event_gives_its_log_provider_id_and_moment_oldest_first():
    lines = shadow_copy_events.lines(_XML)
    assert lines == [
        "  System volsnap id=25 level=3 at@1794564000250 \\Device\\HarddiskVolumeShadowCopy1",
        "  Application VSS id=8224 level=4 at@1794564001500 "
        "The VSS service is shutting down due to idle timeout.",
    ]


def test_the_query_names_the_shadow_copy_providers_and_the_window():
    cmd = shadow_copy_events.command("System", window=600.0)
    assert cmd[:3] == ["wevtutil", "qe", "System"]
    query = next(arg for arg in cmd if arg.startswith("/q:"))
    assert "@Name='VSS'" in query and "@Name='volsnap'" in query
    assert "timediff(@SystemTime) <= 600000" in query


def test_a_log_that_times_out_is_asked_again_after_the_rest():
    """The events of a freeze are logged anyway: past it, a second ask finds them."""
    asked: list[str] = []

    def run(cmd, timeout):
        asked.append(cmd[2])
        if len(asked) <= 2:
            return f"(wevtutil timed out after {timeout:g}s)", False
        return _XML, True

    first = shadow_copy_events.Events(window=600.0, run=run)
    text = first.read()
    assert "timed out" in text
    again = first.read_missed()
    assert asked == ["Application", "System", "Application", "System"]
    assert "id=8224" in again


def test_nothing_missed_reads_nothing_again():
    asked: list[str] = []

    def run(cmd, timeout):
        asked.append(cmd[2])
        return "", True

    events = shadow_copy_events.Events(window=600.0, run=run)
    assert "(none)" in events.read()
    assert events.read_missed() == ""
    assert asked == ["Application", "System"]


@pytest.mark.skipif(sys.platform != "win32", reason="wevtutil is Windows only")
def test_wevtutil_answers_on_this_machine():
    text = shadow_copy_events.Events(window=600.0).read()
    assert "timed out" not in text and "failed" not in text, text
