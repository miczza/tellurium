"""``tellurium mcp --http`` options on the command line, without serving."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")

from tellurium.mcp.config import DEFAULT_IDLE_TIMEOUT, HttpConfig  # noqa: E402


@pytest.fixture
def run(monkeypatch, tmp_path):
    import tellurium.mcp.server as server
    from tellurium.cli import main

    seen: dict = {}
    monkeypatch.setattr(server, "run", lambda config, transport: seen.update(c=config, t=transport))
    monkeypatch.setenv("TELLURIUM_HOME", str(tmp_path))

    def invoke(*argv: str):
        monkeypatch.setattr("sys.argv", ["tellurium", "mcp", *argv])
        main()
        return seen["c"], seen["t"]

    return invoke


def test_http_defaults_loopback_no_eval_and_an_idle_timeout(run):
    config, transport = run("--http", "127.0.0.1:8765")
    assert transport == "http"
    assert config.allow_eval is False
    assert config.http == HttpConfig("127.0.0.1", 8765, DEFAULT_IDLE_TIMEOUT)


def test_http_options(run):
    config, _ = run(
        "--http",
        "localhost:0",
        "--allow-eval",
        "--idle-timeout",
        "0",
    )
    assert config.allow_eval is True
    assert config.http.idle_timeout is None  # 0: never


def test_session_caps(run):
    config, _ = run(
        "--http", "127.0.0.1:0", "--max-sessions-per-client", "2", "--max-sessions", "5"
    )
    assert (config.http.max_sessions_per_client, config.http.max_sessions) == (2, 5)


def test_stdio_keeps_eval_on(run):
    config, transport = run()
    assert transport == "stdio" and config.allow_eval is True and config.http is None


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--idle-timeout", "5"], "need --http"),
        (["--http", "8765"], "HOST:PORT"),
        (["--http", "127.0.0.1:1", "--idle-timeout", "-1"], "--idle-timeout"),
        (["--http", "127.0.0.1:1", "--idle-timeout", "inf"], "--idle-timeout"),
        (["--http", "127.0.0.1:1", "--idle-timeout", "nan"], "--idle-timeout"),
        (["--http", "127.0.0.1:1", "--idle-timeout", "-inf"], "--idle-timeout"),
        (["--http", "192.168.1.5:8765"], "--allow-remote"),
        (["--http", "127.0.0.1:1", "--max-sessions", "0"], "--max-sessions"),
        (["--http", "127.0.0.1:1", "--max-sessions-per-client", "-1"], "--max-sessions-per-client"),
        (["--max-sessions", "3"], "need --http"),
    ],
)
def test_bad_options_exit_with_a_message(run, capsys, argv, message):
    with pytest.raises(SystemExit) as exited:
        run(*argv)
    assert exited.value.code == 2
    assert message in capsys.readouterr().err


def test_non_loopback_bind_with_the_flag_warns(run, capsys):
    config, _ = run("--http", "0.0.0.0:8765", "--allow-remote")
    assert config.http.host == "0.0.0.0"
    assert "WARNING" in capsys.readouterr().err


def test_there_is_no_origin_allowlist(run, capsys):
    with pytest.raises(SystemExit) as exited:
        run("--http", "127.0.0.1:1", "--allow-origin", "https://a.example")
    assert exited.value.code == 2
    assert "--allow-origin" in capsys.readouterr().err  # argparse: unrecognized


def test_idle_timeout_defaults_to_five_minutes(run):
    """A client that dies without ending its MCP session holds its browsers
    (and named profiles) until then."""
    config, _ = run("--http", "127.0.0.1:0")
    assert config.http.idle_timeout == 300
