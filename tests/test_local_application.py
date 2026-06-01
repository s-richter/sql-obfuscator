from pathlib import Path

import pytest

from sql_obfuscator.local_application import LocalWorkspaceApplication
from sql_obfuscator.workflow import (
    DeobfuscationSafetyError,
    ObfuscationOptions,
    TranslationOptions,
)


def test_local_application_prepares_and_inspects_workspace_without_printing(
    tmp_path: Path,
    capsys,
):
    workspace_path = tmp_path / "sample.obf"
    operation = LocalWorkspaceApplication().prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
        options=ObfuscationOptions(seed=42),
    )

    inspection = LocalWorkspaceApplication().inspect_workspace(workspace_path)
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""
    assert operation.workspace_path == workspace_path
    assert operation.prepared.snapshot.obfuscated_sql
    assert workspace_path / "obfuscated.sql" in operation.written_artifact_paths
    assert inspection.seed == 42
    assert inspection.artifacts["obfuscated.sql"] is True


def test_local_application_persists_llm_safe_blocked_workspace(tmp_path: Path):
    workspace_path = tmp_path / "sample.obf"

    operation = LocalWorkspaceApplication().prepare_and_save_workspace(
        "SELECT @UserId, UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
        options=ObfuscationOptions(llm_safe=True),
    )

    assert operation.prepared.safety.approved is False
    assert operation.diagnostics
    assert (workspace_path / "obfuscated.sql").exists()
    assert (workspace_path / "reports" / "privacy_summary.json").exists()


def test_local_application_applies_and_saves_statement_replacements(tmp_path: Path):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "sample.obf"
    prepared = app.prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
        options=ObfuscationOptions(pretty=False),
    ).prepared
    anchor = prepared.snapshot.context_payload["statement_anchors"][0]
    edits_payload = {
        "schema_version": 1,
        "format": "statement_replacements",
        "edits": [
            {
                "statement_id": anchor["statement_id"],
                "sql": f"{anchor['obfuscated_sql']} WHERE 1 = 1",
            }
        ],
    }

    dry_run = app.apply_and_save_statement_replacements(
        workspace_path,
        edits_payload,
        persist=False,
    )
    operation = app.apply_and_save_statement_replacements(workspace_path, edits_payload)

    assert dry_run.written_artifact_paths == ()
    assert (workspace_path / "llm_response_obfuscated.sql").exists()
    assert operation.output_path == workspace_path / "llm_response_obfuscated.sql"
    assert workspace_path / "reports" / "llm_edit_application_report.json" in (
        operation.written_artifact_paths
    )


def test_local_application_validate_before_write_blocks_then_saves(tmp_path: Path):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "sample.obf"
    prepared = app.prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
    ).prepared

    with pytest.raises(DeobfuscationSafetyError, match="unresolved mappings"):
        app.validate_and_save_deobfuscation(
            workspace_path,
            "SELECT unknown_identifier FROM unknown_table;",
        )
    assert (workspace_path / "deobfuscated.sql").exists() is False

    operation = app.validate_and_save_deobfuscation(
        workspace_path,
        prepared.snapshot.obfuscated_sql,
    )

    assert "UserId" in operation.deobfuscation.deobfuscated_sql
    assert workspace_path / "deobfuscated.sql" in operation.written_artifact_paths
    assert workspace_path / "reports" / "deobfuscation_report.json" in (
        operation.written_artifact_paths
    )


def test_local_application_verifies_and_saves_roundtrip_reports(tmp_path: Path):
    workspace_path = tmp_path / "sample.obf"

    operation = LocalWorkspaceApplication().verify_and_save_roundtrip(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
        include_diff_report=True,
    )

    assert operation.roundtrip is not None
    assert workspace_path / "reports" / "roundtrip_report.json" in (
        operation.written_artifact_paths
    )
    assert workspace_path / "reports" / "roundtrip_diff.txt" in (
        operation.written_artifact_paths
    )


def test_local_application_saves_translation_report_and_optional_sql(tmp_path: Path):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "translate.obf"
    options = TranslationOptions(
        source_dialect="tsql",
        target_dialect="hive",
    )

    report_only = app.translate_and_save_artifacts(
        "SELECT [UserId] FROM [Users];",
        options=options,
        workspace_path=workspace_path,
    )
    assert workspace_path / "reports" / "translation_report.json" in (
        report_only.written_artifact_paths
    )
    assert (workspace_path / "translated.sql").exists() is False

    persisted = app.translate_and_save_artifacts(
        "SELECT [UserId] FROM [Users];",
        options=options,
        workspace_path=workspace_path,
        persist_translated_sql=True,
    )
    assert workspace_path / "translated.sql" in persisted.written_artifact_paths
