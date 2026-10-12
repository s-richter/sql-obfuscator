"""The ``sqlobf`` command line.

Five commands and no more; see docs/adr/0006-small-cli.md before adding a command or a
flag that depends on another flag.
"""

from typing import Annotated

import typer

from sql_obfuscator import __version__

app = typer.Typer(
    help="Obfuscate SQL scripts reversibly so they can be shared with an LLM.",
    no_args_is_help=True,
    add_completion=False,
)

# Until a command is implemented it accepts any arguments and says when it will arrive.
_PLACEHOLDER = {"allow_extra_args": True, "ignore_unknown_options": True}


def _not_yet(command: str, milestone: int) -> None:
    typer.echo(f"sqlobf {command} is not implemented yet (milestone {milestone}).", err=True)
    raise typer.Exit(code=2)


def _print_version(value: bool) -> None:
    if value:
        typer.echo(f"sqlobf {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_print_version, is_eager=True, help="Show the version."),
    ] = False,
) -> None:
    pass


@app.command(context_settings=_PLACEHOLDER)
def obfuscate() -> None:
    """Create or update a workspace from one or more scripts."""
    _not_yet("obfuscate", 1)


@app.command(context_settings=_PLACEHOLDER)
def bundle() -> None:
    """Produce instructions, task and obfuscated script for an LLM."""
    _not_yet("bundle", 3)


@app.command(context_settings=_PLACEHOLDER)
def deobfuscate() -> None:
    """Translate any text back to real names using a workspace's mapping."""
    _not_yet("deobfuscate", 1)


@app.command(name="format", context_settings=_PLACEHOLDER)
def format_script() -> None:
    """Pretty-print a script without obfuscating it."""
    _not_yet("format", 1)


@app.command(name="map", context_settings=_PLACEHOLDER)
def show_mapping() -> None:
    """Show, search or export the mapping."""
    _not_yet("map", 1)
