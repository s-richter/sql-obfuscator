"""The command line skeleton."""

import pytest
from typer.testing import CliRunner

from sql_obfuscator import __version__
from sql_obfuscator.cli import app

runner = CliRunner()
COMMANDS = ["obfuscate", "bundle", "deobfuscate", "format", "map"]


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_there_are_exactly_five_commands():
    """ADR 0006. A sixth command needs a decision record, not just a pull request."""
    registered = sorted(
        command.name or command.callback.__name__ for command in app.registered_commands
    )
    assert registered == sorted(COMMANDS)


@pytest.mark.parametrize("command", COMMANDS)
def test_unimplemented_command_says_so_and_fails(command: str):
    result = runner.invoke(app, [command, "some.sql", "--seed", "1"])
    assert result.exit_code == 2
    assert "not implemented yet" in result.output
