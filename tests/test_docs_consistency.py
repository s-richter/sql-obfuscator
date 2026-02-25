from __future__ import annotations

from pathlib import Path

from sql_obfuscator.cli import build_command_parser


def _subparser_help(command: str) -> str:
    parser = build_command_parser()
    subparsers_action = next(
        action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction"
    )
    command_parser = subparsers_action.choices[command]
    return command_parser.format_help()


def test_readme_mentions_key_cli_flags():
    readme_path = Path(__file__).resolve().parents[1] / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")

    for expected in (
        "`--strict-go`",
        "`--stdout-only`",
        "`--output-dir <dir>`",
        "## Current Limits",
    ):
        assert expected in readme_text


def test_readme_and_cli_help_match_recent_flags():
    readme_path = Path(__file__).resolve().parents[1] / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")

    checks = {
        "obfuscate": ("--strict-go", "--stdout-only", "--output-dir"),
        "roundtrip": ("--diff-report", "--stdout-only", "--output-dir"),
        "translate": ("--report-only", "--stdout-only", "--output-dir"),
    }
    for command, flags in checks.items():
        help_text = _subparser_help(command)
        for flag in flags:
            assert flag in help_text
            assert flag in readme_text
