"""The README's "Using tellurium from an LLM agent" example runs as written."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tests.private_temp import private_temp

README = Path(__file__).resolve().parents[2] / "README.md"
SECTION = "## Using tellurium from an LLM agent"


def _section() -> str:
    text = README.read_text()
    start = text.index(SECTION)
    end = text.index("\n## ", start + len(SECTION))
    return text[start:end]


def _block(lang: str) -> str:
    match = re.search(rf"```{lang}\n(.*?)```", _section(), re.S)
    assert match, f"no {lang} block in the README section"
    return match.group(1)


@pytest.fixture(autouse=True)
def private_tempdir(monkeypatch, tmp_path_factory):
    """Temp dirs of this test alone, so the owned download folder is checked here."""
    tmp_path_factory.getbasetemp()
    with private_temp(monkeypatch) as root:
        yield root


async def test_readme_agent_example_runs(local_server, capsys):
    code = _block("python")
    run_line = re.search(r"^asyncio\.run\(main\(.*\)\)$", code, re.M)
    assert run_line, "the example ends with asyncio.run(main(<url>))"
    namespace: dict = {}
    exec(compile(code.replace(run_line.group(0), ""), str(README), "exec"), namespace)
    await namespace["main"](local_server + "/download.html")
    out = capsys.readouterr().out
    assert re.search(r'- link "Report" \[ref=e\d+\]', out)
    saved = re.search(r"^report\.csv (\S+)$", out, re.M)
    assert saved and os.path.isabs(saved.group(1))


async def test_readme_snapshot_sample_matches_the_fixture(browser, local_server):
    tab = await browser.get(local_server + "/download.html")
    actual = await tab.snapshot()
    for line in _block("text").splitlines():
        shape = re.sub(r"\[ref=e\d+\]", "[ref=", line.strip())
        assert any(
            re.sub(r"\[ref=e\d+\]", "[ref=", a.strip()) == shape for a in actual.splitlines()
        ), f"{line!r} not in:\n{actual}"
