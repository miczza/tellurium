from unittest.mock import patch

from tellurium.cli import main


def test_cli_info(capsys):
    with patch("sys.argv", ["tellurium", "info"]):
        main()
    output = capsys.readouterr().out
    assert "Tellurium 0.1.0" in output


def test_cli_no_command(capsys):
    with patch("sys.argv", ["tellurium"]):
        main()
    output = capsys.readouterr().out
    assert "usage" in output.lower() or "tellurium" in output.lower()
