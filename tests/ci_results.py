"""Report of the Windows and macOS CI jobs, from their JUnit artifacts.

``python -m tests.ci_results <artifacts dir>`` with ``CI_OSES`` (the systems,
space separated), ``CI_SHARDS`` (integration shards per system) and
``CI_UNIT`` (``1`` if the unit jobs ran) in the environment. It prints, and
appends to ``$GITHUB_STEP_SUMMARY``, one row per job and the failed tests.
Red tests do not fail it (those jobs are not blocking yet); a job without
its report does (it was cancelled, timed out, or its pytest was killed: on
Windows a ``pytest-timeout`` ends the whole process), and so does a report
without a single test (pytest collected nothing) or with a collection error
(a module that fails at import interrupts the whole job): their tests did
not run.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def expected_names(oses: str, *, shards: int, unit: bool) -> list[str]:
    names = []
    for os_name in oses.split():
        if unit:
            names.append(f"junit-unit-{os_name}")
        names += [f"junit-integration-{os_name}-{n}" for n in range(1, shards + 1)]
    return names


def summarize(root: Path, expected: list[str]) -> tuple[list[str], list[str]]:
    """Markdown lines for the reports under *root*, and the expected ones missing
    or without a single test, or interrupted by a collection error."""
    lines = ["| job | tests | failures | errors | skipped |", "| --- | --- | --- | --- | --- |"]
    red: list[str] = []
    missing = []
    empty = []
    interrupted = []
    for name in expected:
        reports = sorted((root / name).glob("*.xml"))
        if not reports:
            missing.append(name)
            lines.append(f"| {name} | missing | | | |")
            continue
        totals = [0, 0, 0, 0]
        for report in reports:
            for suite in ET.parse(report).getroot().iter("testsuite"):
                for i, key in enumerate(("tests", "failures", "errors", "skipped")):
                    totals[i] += int(suite.get(key, 0))
                for case in suite.iter("testcase"):
                    error = case.find("error")
                    if error is not None and error.get("message") == "collection failure":
                        # pytest stops the job: none of its tests ran.
                        interrupted.append(f"{name} (`{case.get('name')}`)")
                    if case.find("failure") is not None or error is not None:
                        red.append(f"- {name}: `{case.get('classname')}::{case.get('name')}`")
        if totals[0] == 0:
            # pytest wrote a report but collected nothing (a wrong path, exit code 4).
            empty.append(name)
            lines.append(f"| {name} | no tests | | | |")
            continue
        lines.append(f"| {name} | " + " | ".join(map(str, totals)) + " |")
    if red:
        lines += ["", "Failed:", *red]
    if missing:
        lines += ["", "No report (cancelled, timed out or killed): " + ", ".join(missing)]
    if empty:
        lines += ["", "The report ran no tests (nothing collected): " + ", ".join(empty)]
    if interrupted:
        lines += ["", "A collection error stopped the job: " + ", ".join(interrupted)]
    stopped = dict.fromkeys(entry.split(" ", 1)[0] for entry in interrupted)
    return lines, missing + empty + list(stopped)


def main(argv: list[str], expected: list[str] | None = None) -> int:
    if expected is None:
        expected = expected_names(
            os.environ["CI_OSES"],
            shards=int(os.environ["CI_SHARDS"]),
            unit=os.environ.get("CI_UNIT") == "1",
        )
    lines, missing = summarize(Path(argv[0]), expected)
    text = "\n".join(lines) + "\n"
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
