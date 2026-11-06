"""The CI's report of the Windows and macOS jobs: a missing JUnit report (a
shard cancelled, timed out or killed) fails the run, red tests do not."""

from __future__ import annotations

from tests import ci_results

_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="{e}" failures="{f}" skipped="1" tests="5">
<testcase classname="tests.integration.test_a" name="test_ok" time="1.0"/>
<testcase classname="tests.integration.test_a" name="test_red" time="1.0"><failure message="boom"/></testcase>
</testsuite></testsuites>
"""


def _report(root, name, failures=1, errors=0):
    folder = root / name
    folder.mkdir()
    (folder / "junit.xml").write_text(_JUNIT.format(f=failures, e=errors))


def test_red_tests_are_listed_but_do_not_fail(tmp_path):
    _report(tmp_path, "junit-integration-macos-15-1")
    lines, missing = ci_results.summarize(tmp_path, ["junit-integration-macos-15-1"])
    assert missing == []
    text = "\n".join(lines)
    assert "tests.integration.test_a::test_red" in text
    assert "| junit-integration-macos-15-1 | 5 | 1 | 0 | 1 |" in text


def test_a_missing_report_is_named_and_fails(tmp_path, capsys):
    _report(tmp_path, "junit-unit-macos-15")
    expected = ci_results.expected_names("windows-2025 macos-15", shards=2, unit=True)
    assert ci_results.main([str(tmp_path)], expected) == 1
    out = capsys.readouterr().out
    assert "junit-integration-windows-2025-2" in out and "missing" in out


def test_expected_names_follow_the_matrix():
    assert ci_results.expected_names("macos-15", shards=1, unit=False) == [
        "junit-integration-macos-15-1"
    ]


def test_the_chrome_check_reads_the_major_of_a_user_agent():
    from tests import ci_chrome

    ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome/157.0.0.0 Safari"
    assert ci_chrome.ua_major(ua) == 157


def test_a_report_without_tests_fails_like_a_missing_one(tmp_path, capsys):
    # pytest that collects nothing (a wrong path: exit code 4) still writes a report.
    folder = tmp_path / "junit-integration-windows-2025-1"
    folder.mkdir()
    (folder / "junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites>'
        '<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="0"/></testsuites>'
    )
    assert ci_results.main([str(tmp_path)], ["junit-integration-windows-2025-1"]) == 1
    out = capsys.readouterr().out
    assert "| junit-integration-windows-2025-1 | no tests |" in out
    assert "ran no tests" in out


def test_a_collection_error_fails_the_run(tmp_path, capsys):
    # A module that fails at import stops the shard ("Interrupted"): its other
    # files never run, and the report holds just that one error.
    folder = tmp_path / "junit-integration-windows-2025-1"
    folder.mkdir()
    (folder / "junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites>'
        '<testsuite name="pytest" errors="1" failures="0" skipped="0" tests="1">'
        '<testcase classname="" name="tests.integration.test_bad" time="0.000">'
        '<error message="collection failure">ImportError</error></testcase>'
        "</testsuite></testsuites>"
    )
    assert ci_results.main([str(tmp_path)], ["junit-integration-windows-2025-1"]) == 1
    out = capsys.readouterr().out
    assert "tests.integration.test_bad" in out
    assert "collection" in out


def test_an_error_in_a_test_setup_is_only_listed(tmp_path):
    folder = tmp_path / "junit-unit-macos-15"
    folder.mkdir()
    (folder / "junit.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites>'
        '<testsuite name="pytest" errors="1" failures="0" skipped="0" tests="2">'
        '<testcase classname="tests.unit.test_a" name="test_ok" time="0.1"/>'
        '<testcase classname="tests.unit.test_a" name="test_b" time="0.1">'
        '<error message="failed on setup with &quot;boom&quot;">x</error></testcase>'
        "</testsuite></testsuites>"
    )
    lines, failing = ci_results.summarize(tmp_path, ["junit-unit-macos-15"])
    assert failing == []
