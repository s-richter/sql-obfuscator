from pathlib import Path

import pytest

from sql_obfuscator.errors import WorkspaceError
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
    artifacts = {artifact.relative_path: artifact for artifact in inspection.artifact_statuses}
    assert artifacts["obfuscated.sql"].available is True
    assert artifacts["obfuscated.sql"].media_type == "text/sql"
    assert artifacts["obfuscated.sql"].read_only is True
    assert artifacts["obfuscated.sql"].integrity_protected is True
    assert artifacts["translated.sql"].available is False


def test_local_application_exposes_sqlglot_warning_diagnostics_without_printing(
    tmp_path: Path,
    capsys,
):
    operation = LocalWorkspaceApplication().prepare_and_save_workspace(
        "BEGIN TRY SELECT UserId FROM Users END TRY BEGIN CATCH SELECT 2 END CATCH;",
        input_path=tmp_path / "sample.sql",
        workspace_path=tmp_path / "sample.obf",
    )

    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err == ""
    assert any(
        diagnostic.code == "sqlglot.fallback_parse"
        for diagnostic in operation.diagnostics
    )


def test_local_application_opens_workspace_as_read_only_artifact_tree(tmp_path: Path):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "sample.obf"
    app.prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
    )

    workspace = app.open_workspace(workspace_path)
    artifacts = {artifact.relative_path: artifact for artifact in workspace.artifacts}

    assert workspace.workspace_path == workspace_path
    assert workspace.inspection.artifacts["obfuscated.sql"] is True
    assert workspace.artifacts == workspace.inspection.artifact_statuses
    assert artifacts["original.sql"].available is True
    assert artifacts["original.sql"].read_only is True
    assert artifacts["original.sql"].integrity_protected is True
    assert artifacts["llm_instructions.md"].media_type == "text/markdown"
    assert artifacts["mapping.json"].kind == "mapping"
    assert artifacts["reports/roundtrip_report.json"].available is False


def test_local_application_loads_known_workspace_artifact_content(tmp_path: Path):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "sample.obf"
    app.prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
    )

    content = app.load_workspace_artifact(workspace_path, "original.sql")

    assert content.artifact.relative_path == "original.sql"
    assert content.artifact.media_type == "text/sql"
    assert content.text == "SELECT UserId FROM Users;"


@pytest.mark.parametrize(
    "relative_path, expected_message",
    [
        ("../outside.sql", "must stay within the workspace"),
        ("reports/../../outside.sql", "must stay within the workspace"),
        ("unknown.sql", "Unknown workspace artifact path"),
        ("translated.sql", "Workspace artifact is not available"),
    ],
)
def test_local_application_rejects_unsafe_or_unavailable_workspace_artifacts(
    tmp_path: Path,
    relative_path: str,
    expected_message: str,
):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "sample.obf"
    app.prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
    )

    with pytest.raises(WorkspaceError, match=expected_message):
        app.load_workspace_artifact(workspace_path, relative_path)


def test_local_application_rejects_absolute_workspace_artifact_path(tmp_path: Path):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "sample.obf"
    app.prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
    )

    with pytest.raises(WorkspaceError, match="must stay within the workspace"):
        app.load_workspace_artifact(workspace_path, tmp_path / "outside.sql")


def test_local_application_rejects_workspace_artifact_symlink_escape(tmp_path: Path):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "sample.obf"
    app.prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
    )
    outside_path = tmp_path / "outside.md"
    outside_path.write_text("outside", encoding="utf-8")
    artifact_path = workspace_path / "llm_instructions.md"
    artifact_path.unlink()
    try:
        artifact_path.symlink_to(outside_path)
    except OSError:
        pytest.skip("Platform cannot create symlinks")

    with pytest.raises(WorkspaceError, match="must stay within the workspace"):
        app.load_workspace_artifact(workspace_path, "llm_instructions.md")


def test_local_application_validates_integrity_before_loading_workspace_artifact(tmp_path: Path):
    app = LocalWorkspaceApplication()
    workspace_path = tmp_path / "sample.obf"
    app.prepare_and_save_workspace(
        "SELECT UserId FROM Users;",
        input_path=tmp_path / "sample.sql",
        workspace_path=workspace_path,
    )
    mapping_path = workspace_path / "mapping.json"
    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="Integrity check failed"):
        app.load_workspace_artifact(workspace_path, "llm_instructions.md")


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
