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


def test_cli_reference_mentions_key_cli_flags():
    root = Path(__file__).resolve().parents[1]
    readme_text = (root / "README.md").read_text(encoding="utf-8")
    reference_text = (root / "docs" / "reference" / "cli.md").read_text(encoding="utf-8")

    for expected in (
        "`--strict-go`",
        "`--stdout-only`",
        "`--output-dir <dir>`",
    ):
        assert expected in reference_text
    assert "## Current Limits" in readme_text


def test_cli_reference_and_cli_help_match_recent_flags():
    root = Path(__file__).resolve().parents[1]
    reference_text = (root / "docs" / "reference" / "cli.md").read_text(encoding="utf-8")

    checks = {
        "obfuscate": ("--strict-go", "--stdout-only", "--output-dir"),
        "roundtrip": ("--diff-report", "--stdout-only", "--output-dir"),
        "translate": ("--report-only", "--stdout-only", "--output-dir"),
    }
    for command, flags in checks.items():
        help_text = _subparser_help(command)
        for flag in flags:
            assert flag in help_text
            assert flag in reference_text


def test_docs_describe_translate_stdout_only_semantics():
    root = Path(__file__).resolve().parents[1]
    reference_text = (root / "docs" / "reference" / "cli.md").read_text(encoding="utf-8")

    assert "`--stdout-only` | Print summary and SQL; write no translated SQL file." in reference_text
    assert "the workspace also stores `translated.sql`" in reference_text


def test_storage_seam_decision_is_recorded_as_durable_architecture_doc():
    root = Path(__file__).resolve().parents[1]
    adr_text = (
        root / "docs" / "adr" / "0001-local-workspace-store-storage-seam.md"
    ).read_text(encoding="utf-8")

    assert "LocalWorkspaceStore" in adr_text
    assert "WorkspaceStore protocol" in adr_text
    assert "defer" in adr_text.lower()
    for trigger in (
        "web tenant storage",
        "desktop project storage",
        "non-local adapter",
    ):
        assert trigger in adr_text


def test_docs_index_links_to_storage_seam_decision():
    root = Path(__file__).resolve().parents[1]
    docs_index = (root / "docs" / "README.md").read_text(encoding="utf-8")

    assert "ADR 0001" in docs_index
    assert "adr/0001-local-workspace-store-storage-seam.md" in docs_index
