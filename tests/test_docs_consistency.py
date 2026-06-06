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


def test_readme_external_llm_example_describes_redaction_mode_flag():
    root = Path(__file__).resolve().parents[1]
    readme_text = (root / "README.md").read_text(encoding="utf-8")

    assert "`--redaction-mode irreversible`" in readme_text
    assert "without preserving original values for restoration" in readme_text


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
    assert "tenant web storage" in adr_text
    assert "`tenant_id`" in adr_text
    assert "`workspace_id`" in adr_text
    assert "opaque server-generated workspace ID" in adr_text
    assert "Minimum Contract Tests For Tenant Web Storage" in adr_text
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


def test_website_hosting_guardrails_are_recorded_as_durable_architecture_doc():
    root = Path(__file__).resolve().parents[1]
    guardrails_text = (
        root
        / "docs"
        / "maintainers"
        / "architecture"
        / "website-hosting-guardrails-2026-06-06.md"
    ).read_text(encoding="utf-8")
    docs_index = (root / "docs" / "README.md").read_text(encoding="utf-8")

    assert "tenant_id" in guardrails_text
    assert "workspace_id" in guardrails_text
    assert "opaque server-generated workspace IDs" in guardrails_text
    assert "Callers must never\nprovide filesystem paths" in guardrails_text
    assert "fail closed by default" in guardrails_text
    assert "maximum SQL input bytes" in guardrails_text
    assert "per-workspace mutation lock" in guardrails_text
    assert "Website hosting guardrails" in docs_index
    assert "website-hosting-guardrails-2026-06-06.md" in docs_index


def test_python_api_docs_direct_new_persistence_to_local_store_or_application():
    root = Path(__file__).resolve().parents[1]
    reference_text = (root / "docs" / "reference" / "python-api.md").read_text(
        encoding="utf-8"
    )

    assert "`sql_obfuscator.workspace` remain available as compatibility delegators" in reference_text
    assert "New local persistence behavior should use" in reference_text
    assert "`LocalWorkspaceStore` or `LocalWorkspaceApplication`" in reference_text
    assert "not expand the compatibility surface" in reference_text
