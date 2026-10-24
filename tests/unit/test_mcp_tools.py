"""The MCP layer without Chrome: argument whitelist, tool set, error messages,
results, dispatch through a real in-process MCP client, and the base package
working without the ``mcp`` extra."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("mcp")

from tellurium.browser.geometry import ElementNotHittableError  # noqa: E402
from tellurium.browser.handles import StaleElementError  # noqa: E402
from tellurium.browser.snapshot import SnapshotTooLargeError  # noqa: E402
from tellurium.mcp.results import Reply, ToolError, explain  # noqa: E402
from tellurium.mcp.tool import Tool, ToolArgumentError, param  # noqa: E402


async def _noop(pool, args):
    return Reply("done", {"ok": True})


def _tool(**kw):
    defaults = {
        "name": "demo",
        "description": "a demo",
        "handler": _noop,
        "params": {
            "ref": param("string", "a ref"),
            "count": param("integer", "how many"),
            "human": param("boolean", "human input"),
            "mode": param("string", "a mode", enum=["a", "b"]),
        },
        "required": ("ref",),
    }
    return Tool(**{**defaults, **kw})


# --------------------------------------------------------------------------- #
# Arguments: a whitelist checked against the schema
# --------------------------------------------------------------------------- #


def test_unknown_argument_is_refused_and_named():
    with pytest.raises(ToolArgumentError, match="'colour'.*allowed: count, human, mode, ref"):
        _tool().check({"ref": "e1", "colour": "red"})


def test_missing_required_argument():
    with pytest.raises(ToolArgumentError, match="missing required argument 'ref'"):
        _tool().check({})


def test_wrong_types_are_refused():
    with pytest.raises(ToolArgumentError, match="'count' must be integer"):
        _tool().check({"ref": "e1", "count": "3"})
    with pytest.raises(ToolArgumentError, match="'count' must be integer"):
        _tool().check({"ref": "e1", "count": True})  # bool is not an integer here
    with pytest.raises(ToolArgumentError, match="'human' must be boolean"):
        _tool().check({"ref": "e1", "human": "yes"})
    with pytest.raises(ToolArgumentError, match="'mode' must be one of"):
        _tool().check({"ref": "e1", "mode": "c"})


def test_valid_arguments_pass_through_with_none_as_empty():
    assert _tool().check({"ref": "e1", "count": 2}) == {"ref": "e1", "count": 2}
    assert _tool(required=()).check(None) == {}


def test_page_tool_requires_target_id():
    tool = _tool(page=True)
    with pytest.raises(ToolArgumentError, match="missing required argument 'targetId'"):
        tool.check({"ref": "e1"})
    schema = tool.input_schema()
    assert schema["required"][0] == "targetId"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["targetId"]["type"] == "string"


# --------------------------------------------------------------------------- #
# Errors: a message telling the agent what to do next
# --------------------------------------------------------------------------- #


def test_stale_ref_says_take_a_new_snapshot():
    message = explain(StaleElementError("Ref @e3 belongs to a previous document"))
    assert "snapshot" in message.lower() and "@e3" in message


def test_not_hittable_names_what_covers_it():
    exc = ElementNotHittableError('Element is not under the pointer: <div id="overlay"> is on top')
    message = explain(exc)
    assert 'div id="overlay"' in message and "covered" in message.lower()


def test_snapshot_too_large_suggests_selector_or_interactive():
    message = explain(SnapshotTooLargeError("page has 90000 nodes"))
    assert "selector" in message and "interactive" in message


def test_stale_ref_advice_is_given_once():
    exc = StaleElementError("Ref @e3 belongs to a previous document: take a new snapshot")
    assert explain(exc).lower().count("snapshot") == 1


def test_unknown_ref_and_tool_errors_and_timeouts():
    unknown = explain(LookupError("No element with ref @e9: take a snapshot first"))
    assert unknown.lower().count("snapshot") == 1
    assert explain(ToolError("Unknown targetId 't9'")) == "Unknown targetId 't9'"
    assert "timed out" in explain(TimeoutError("waited 5s")).lower()
    assert "timed out" in explain(asyncio.TimeoutError()).lower()
    assert explain(ValueError("boom")) == "ValueError: boom"


def test_selector_without_match_does_not_talk_about_refs():
    message = explain(LookupError("No element matching '#nope'"))
    assert "#nope" in message and "selector" in message and "ref" not in message.lower()


def test_chrome_errors_are_translated():
    from tellurium.browser.launcher import LaunchError
    from tellurium.cdp.types import CDPError

    focus = explain(CDPError("Element is not focusable", -32000))
    assert "cannot take keyboard focus" in focus and "text field" in focus
    url = explain(CDPError("Cannot navigate to invalid URL", -32000))
    assert "Invalid URL" in url and "https://" in url
    locked = explain(
        LaunchError(
            "Chrome exited during launch (exit code 21). Its last output:\n"
            "Failed to create /x/SingletonLock: File exists (17)"
        )
    )
    assert "already open in another process" in locked and "SingletonLock" not in locked


# --------------------------------------------------------------------------- #
# Base package without the extra
# --------------------------------------------------------------------------- #


def _run_without_mcp(code: str) -> subprocess.CompletedProcess[str]:
    prelude = "import sys; sys.modules['mcp'] = None\n"  # import mcp -> ImportError
    return subprocess.run(
        [sys.executable, "-c", prelude + textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_base_package_imports_without_mcp():
    done = _run_without_mcp(
        """
        import tellurium
        from tellurium import Browser, Session
        print("ok", "tellurium.mcp" not in sys.modules)
        """
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok True"


def test_cli_mcp_without_extra_prints_the_install_command():
    done = _run_without_mcp(
        """
        sys.argv = ["tellurium", "mcp"]
        from tellurium.cli import main
        main()
        """
    )
    assert done.returncode == 2
    assert "pip install 'tellurium[mcp]'" in done.stderr
    assert done.stdout == ""


# --------------------------------------------------------------------------- #
# Small rules of the tools
# --------------------------------------------------------------------------- #


def test_download_names_never_overwrite_or_escape(tmp_path):
    from tellurium.mcp.actions import _free_path

    first = _free_path(tmp_path / "dl", "report.csv")
    assert first == tmp_path / "dl" / "report.csv"
    first.write_text("x")
    assert _free_path(tmp_path / "dl", "report.csv").name == "report (1).csv"
    assert _free_path(tmp_path / "dl", "../../etc/passwd").parent == tmp_path / "dl"
    for odd in ("", ".", ".."):
        assert _free_path(tmp_path / "dl", odd).name == "download"


async def test_malformed_ref_is_refused_before_touching_the_page():
    from tellurium.mcp.pages import ref_element

    class _NoTab:
        async def select(self, selector):
            raise AssertionError("must not be reached")

    with pytest.raises(ToolError, match="ref must look like 'e12'"):
        await ref_element(_NoTab(), "button.submit")


def test_session_names_are_safe_directory_names():
    from tellurium.mcp.sessions import _check_name

    for good in ("github", "work.2", "a_b-c"):
        _check_name(good)
    for bad in ("../x", ".hidden", "", "a/b", "x" * 65, "temp-3"):
        with pytest.raises(ToolError, match="Invalid session name"):
            _check_name(bad)
