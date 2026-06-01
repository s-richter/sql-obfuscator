from __future__ import annotations

import json

from pathlib import Path

import pytest

from sql_obfuscator.errors import WorkspaceError
from sql_obfuscator.local_workspace_store import LocalWorkspaceStore
from sql_obfuscator.workflow import ObfuscationOptions, prepare_workspace
from sql_obfuscator.workspace import (
    WorkspaceSnapshot,
    default_workspace_path,
    load_workspace_snapshot,
    load_context_payload,
    load_llm_workflow_report,
    load_mapping_payload,
    load_privacy_summary_report,
    load_redaction_payload,
    save_llm_workflow_report_if_present,
    save_workspace_snapshot,
    save_workspace_artifacts,
    save_translation_artifacts,
)


def test_default_workspace_path_uses_stem(tmp_path: Path):
    input_path = tmp_path / "sample.sql"
    workspace = default_workspace_path(input_path)
    assert workspace == tmp_path / "sample.obf"


def test_local_workspace_store_saves_and_loads_snapshot(tmp_path: Path):
    store = LocalWorkspaceStore()
    input_path = tmp_path / "sample.sql"
    workspace_path = tmp_path / "sample.obf"
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name=input_path.name,
        options=ObfuscationOptions(seed=42),
    )

    store.save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=prepared.original_sql,
        snapshot=prepared.snapshot,
        instructions_text=prepared.instructions_text,
    )

    assert store.load_workspace_snapshot(workspace_path) == prepared.snapshot
    assert store.default_workspace_path(input_path) == workspace_path


def test_local_workspace_store_rejects_integrity_tampering(tmp_path: Path):
    store = LocalWorkspaceStore()
    input_path = tmp_path / "sample.sql"
    workspace_path = tmp_path / "sample.obf"
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name=input_path.name,
    )
    store.save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=prepared.original_sql,
        snapshot=prepared.snapshot,
    )
    mapping_path = workspace_path / "mapping.json"
    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="Integrity check failed"):
        store.load_workspace_snapshot(workspace_path)


def test_local_workspace_store_inspects_workspace_artifacts(tmp_path: Path):
    store = LocalWorkspaceStore()
    input_path = tmp_path / "sample.sql"
    workspace_path = tmp_path / "sample.obf"
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name=input_path.name,
        options=ObfuscationOptions(seed=42),
    )
    store.save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=prepared.original_sql,
        snapshot=prepared.snapshot,
    )

    inspection = store.inspect_workspace(workspace_path)

    assert inspection.workspace_path == workspace_path
    assert inspection.dialect == "tsql"
    assert inspection.seed == 42
    assert inspection.statement_count == 1
    assert inspection.statement_anchor_count == 1
    assert inspection.mapping_entry_count > 0
    assert inspection.integrity_algorithm == "sha256"
    assert inspection.integrity_tracked_file_count == 4
    assert inspection.privacy_llm_safe_blocked is False
    assert inspection.artifacts["original.sql"] is True
    assert inspection.artifacts["reports/privacy_summary.json"] is True
    assert inspection.artifacts["translated.sql"] is False


def test_local_workspace_store_inspect_rejects_missing_workspace(tmp_path: Path):
    with pytest.raises(WorkspaceError, match="Workspace not found"):
        LocalWorkspaceStore().inspect_workspace(tmp_path / "missing.obf")


def test_local_workspace_store_inspect_rejects_integrity_tampering(tmp_path: Path):
    store = LocalWorkspaceStore()
    input_path = tmp_path / "sample.sql"
    workspace_path = tmp_path / "sample.obf"
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name=input_path.name,
    )
    store.save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=prepared.original_sql,
        snapshot=prepared.snapshot,
    )
    mapping_path = workspace_path / "mapping.json"
    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="Integrity check failed"):
        store.inspect_workspace(workspace_path)


def test_save_and_load_workspace_snapshot_preserves_prepared_workspace(tmp_path: Path):
    input_path = tmp_path / "sample.sql"
    workspace_path = tmp_path / "sample.obf"
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name=input_path.name,
        options=ObfuscationOptions(seed=42),
    )

    save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=prepared.original_sql,
        snapshot=prepared.snapshot,
        instructions_text=prepared.instructions_text,
    )
    loaded = load_workspace_snapshot(workspace_path)

    assert loaded == prepared.snapshot
    assert (workspace_path / "llm_instructions.md").read_text(encoding="utf-8") == prepared.instructions_text
    assert (workspace_path / "reports" / "llm_workflow_report.json").exists()
    assert (workspace_path / "reports" / "privacy_summary.json").exists()


def test_save_and_load_workspace_snapshot_preserves_reversible_redaction(tmp_path: Path):
    input_path = tmp_path / "sample.sql"
    workspace_path = tmp_path / "sample.obf"
    prepared = prepare_workspace(
        "SELECT UserId FROM Users WHERE Status = 'secret';",
        input_name=input_path.name,
        options=ObfuscationOptions(
            redact_literals=True,
            redaction_mode="reversible",
        ),
    )

    save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=prepared.original_sql,
        snapshot=prepared.snapshot,
        instructions_text=prepared.instructions_text,
    )
    loaded = load_workspace_snapshot(workspace_path)

    assert loaded.redaction_payload == prepared.snapshot.redaction_payload
    assert (workspace_path / "redaction.json").exists()
    assert (workspace_path / "redaction.schema.json").exists()


def test_load_workspace_snapshot_rejects_integrity_tampering(tmp_path: Path):
    input_path = tmp_path / "sample.sql"
    workspace_path = tmp_path / "sample.obf"
    prepared = prepare_workspace(
        "SELECT UserId FROM Users;",
        input_name=input_path.name,
    )
    save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=prepared.original_sql,
        snapshot=prepared.snapshot,
    )
    mapping_path = workspace_path / "mapping.json"
    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="Integrity check failed"):
        load_workspace_snapshot(workspace_path)


def test_save_llm_workflow_report_if_present_updates_only_existing_report(tmp_path: Path):
    workspace_path = tmp_path / "sample.obf"
    workspace_path.mkdir()
    report_payload = {
        "schema_version": 1,
        "llm_safe_requested": False,
        "llm_safe_approved": True,
        "obfuscation_summary": {},
        "deobfuscation_summary": {"unknown_count": 0},
        "recommendations": [],
    }

    save_llm_workflow_report_if_present(
        workspace_path=workspace_path,
        report_payload=report_payload,
    )
    assert (workspace_path / "reports" / "llm_workflow_report.json").exists() is False

    input_path = tmp_path / "sample.sql"
    prepared = prepare_workspace("SELECT UserId FROM Users;", input_name=input_path.name)
    save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=prepared.original_sql,
        snapshot=prepared.snapshot,
    )
    save_llm_workflow_report_if_present(
        workspace_path=workspace_path,
        report_payload=report_payload,
    )

    assert load_llm_workflow_report(
        workspace_path / "reports" / "llm_workflow_report.json"
    ) == report_payload


def test_save_workspace_snapshot_preserves_absent_optional_reports(tmp_path: Path):
    workspace_path = tmp_path / "sample.obf"
    snapshot = WorkspaceSnapshot(
        obfuscated_sql="SELECT 1;",
        mapping_payload={
            "schema_version": 1,
            "entries": [],
            "forward_index": {},
            "reverse_index": {},
        },
        context_payload={
            "schema_version": 1,
            "dialect": "tsql",
            "seed": None,
            "pretty": True,
            "batch_count": 1,
            "statement_count": 1,
            "mapping_entry_count": 0,
        },
        redaction_payload=None,
        privacy_summary={},
        llm_workflow_report={},
    )

    save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=tmp_path / "sample.sql",
        original_sql="SELECT 1;",
        snapshot=snapshot,
    )

    assert (workspace_path / "reports" / "privacy_summary.json").exists() is False
    assert (workspace_path / "reports" / "llm_workflow_report.json").exists() is False
    assert load_workspace_snapshot(workspace_path) == snapshot


def test_load_mapping_payload_rejects_invalid_schema(tmp_path: Path):
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        '{"schema_version": 99, "entries": [], "forward_index": {}, "reverse_index": {}}',
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="Unsupported mapping schema"):
        load_mapping_payload(mapping_path)


def test_load_context_payload_rejects_missing_required_fields(tmp_path: Path):
    context_path = tmp_path / "context.json"
    context_path.write_text(
        '{"schema_version": 1, "dialect": "tsql"}',
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="missing/invalid field"):
        load_context_payload(context_path)


def test_load_context_payload_accepts_statement_anchors(tmp_path: Path):
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "input_file": "sample.sql",
                "dialect": "tsql",
                "pretty": True,
                "batch_count": 1,
                "statement_count": 1,
                "mapping_entry_count": 0,
                "statement_anchors": [
                    {
                        "statement_id": "stmt_0001",
                        "batch_index": 1,
                        "statement_index": 1,
                        "global_statement_index": 1,
                        "statement_kind": "select",
                        "fingerprint": "abc123",
                        "identifier_tokens": ["x"],
                        "placeholder_tokens": [],
                        "fallback_preserved": False,
                        "preview": "SELECT x",
                        "obfuscated_sql": "SELECT x",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = load_context_payload(context_path)
    assert payload["statement_anchors"][0]["statement_id"] == "stmt_0001"



def test_load_context_payload_rejects_invalid_statement_anchor_shape(tmp_path: Path):
    context_path = tmp_path / "context.json"
    context_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "input_file": "sample.sql",
                "dialect": "tsql",
                "pretty": True,
                "batch_count": 1,
                "statement_count": 1,
                "mapping_entry_count": 0,
                "statement_anchors": [
                    {
                        "statement_id": "stmt_0001",
                        "batch_index": 1,
                        "statement_index": 1,
                        "global_statement_index": 1,
                        "statement_kind": "select",
                        "fingerprint": "abc123",
                        "identifier_tokens": "bad",
                        "placeholder_tokens": [],
                        "fallback_preserved": False,
                        "preview": "SELECT x",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="statement anchor field 'identifier_tokens'"):
        load_context_payload(context_path)


def test_load_mapping_payload_rejects_missing_indexes(tmp_path: Path):
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text('{"schema_version": 1, "entries": []}', encoding="utf-8")

    with pytest.raises(WorkspaceError, match="forward_index"):
        load_mapping_payload(mapping_path)


def test_save_translation_artifacts_writes_report_and_optional_sql(tmp_path: Path):
    workspace = tmp_path / "translate_ws"
    payload = {
        "source_dialect": "tsql",
        "target_dialect": "hive",
        "batch_count": 1,
        "statement_count": 1,
        "translated_statement_count": 1,
        "failed_statement_count": 0,
        "warnings": [],
        "failures": [],
        "validated": True,
    }
    save_translation_artifacts(
        workspace_path=workspace,
        report_payload=payload,
        translated_sql="SELECT 1",
    )
    assert (workspace / "translated.sql").exists()
    assert (workspace / "reports" / "translation_report.json").exists()
    assert (workspace / "reports" / "translation_report.schema.json").exists()


def test_save_translation_artifacts_removes_stale_translated_sql_when_not_provided(tmp_path: Path):
    workspace = tmp_path / "translate_ws"
    payload = {
        "source_dialect": "tsql",
        "target_dialect": "hive",
        "batch_count": 1,
        "statement_count": 1,
        "translated_statement_count": 1,
        "failed_statement_count": 0,
        "warnings": [],
        "failures": [],
        "validated": True,
    }
    save_translation_artifacts(
        workspace_path=workspace,
        report_payload=payload,
        translated_sql="SELECT 1",
    )
    assert (workspace / "translated.sql").exists()

    save_translation_artifacts(
        workspace_path=workspace,
        report_payload=payload,
        translated_sql=None,
    )
    assert (workspace / "translated.sql").exists() is False


def test_save_workspace_artifacts_removes_stale_redaction_files(tmp_path: Path):
    workspace = tmp_path / "sample.obf"
    mapping_payload = {
        "schema_version": 1,
        "entries": [],
        "forward_index": {},
        "reverse_index": {},
    }
    context_payload = {
        "schema_version": 1,
        "dialect": "tsql",
        "seed": None,
        "pretty": True,
        "redact_literals": True,
        "strip_comments": False,
        "redaction_mode": "reversible",
        "redaction_policy": "all",
        "sensitive_columns": [],
        "batch_count": 1,
        "statement_count": 1,
        "mapping_entry_count": 0,
    }
    redaction_payload = {
        "schema_version": 1,
        "mode": "reversible",
        "entries": [
            {
                "placeholder": "__SQL_OBFUSCATOR_STR_000001__",
                "original_this": "secret",
                "is_string": True,
            }
        ],
    }
    save_workspace_artifacts(
        workspace_path=workspace,
        input_path=tmp_path / "one.sql",
        original_sql="SELECT 'secret';",
        obfuscated_sql="SELECT '__SQL_OBFUSCATOR_STR_000001__';",
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        redaction_payload=redaction_payload,
    )
    assert (workspace / "redaction.json").exists()
    assert (workspace / "redaction.schema.json").exists()

    context_payload = dict(context_payload)
    context_payload["redaction_mode"] = "none"
    context_payload["redact_literals"] = False
    save_workspace_artifacts(
        workspace_path=workspace,
        input_path=tmp_path / "two.sql",
        original_sql="SELECT 1;",
        obfuscated_sql="SELECT 1;",
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        redaction_payload=None,
    )
    assert (workspace / "redaction.json").exists() is False
    assert (workspace / "redaction.schema.json").exists() is False


def test_load_redaction_payload_valid(tmp_path: Path):
    redaction_path = tmp_path / "redaction.json"
    redaction_path.write_text(
        (
            '{"schema_version": 1, "mode": "reversible", "entries": '
            '[{"placeholder": "__SQL_OBFUSCATOR_STR_000001__", "original_this": "secret", "is_string": true}]}'
        ),
        encoding="utf-8",
    )

    payload = load_redaction_payload(redaction_path)
    assert payload["schema_version"] == 1
    assert payload["mode"] == "reversible"
    assert len(payload["entries"]) == 1


def test_load_redaction_payload_rejects_invalid_schema(tmp_path: Path):
    redaction_path = tmp_path / "redaction.json"
    redaction_path.write_text(
        '{"schema_version": 2, "mode": "reversible", "entries": []}',
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="Unsupported redaction schema"):
        load_redaction_payload(redaction_path)


def test_load_redaction_payload_rejects_invalid_mode(tmp_path: Path):
    redaction_path = tmp_path / "redaction.json"
    redaction_path.write_text(
        '{"schema_version": 1, "mode": "irreversible", "entries": []}',
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="Unsupported redaction mode"):
        load_redaction_payload(redaction_path)


def test_load_redaction_payload_rejects_invalid_entry_shape(tmp_path: Path):
    redaction_path = tmp_path / "redaction.json"
    redaction_path.write_text(
        (
            '{"schema_version": 1, "mode": "reversible", "entries": '
            '[{"placeholder": "__SQL_OBFUSCATOR_STR_000001__", "original_this": 123, "is_string": true}]}'
        ),
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="missing/invalid field 'original_this'"):
        load_redaction_payload(redaction_path)



def test_save_workspace_artifacts_removes_stale_llm_workflow_report(tmp_path: Path):
    workspace = tmp_path / "sample.obf"
    mapping_payload = {
        "schema_version": 1,
        "entries": [],
        "forward_index": {},
        "reverse_index": {},
    }
    context_payload = {
        "schema_version": 1,
        "dialect": "tsql",
        "seed": None,
        "pretty": True,
        "redact_literals": False,
        "strip_comments": False,
        "redaction_mode": "none",
        "redaction_policy": "all",
        "sensitive_columns": [],
        "batch_count": 1,
        "statement_count": 1,
        "mapping_entry_count": 0,
    }
    llm_workflow_report = {
        "schema_version": 1,
        "llm_safe_requested": True,
        "llm_safe_approved": True,
        "obfuscation_summary": {"statement_count": 1},
        "deobfuscation_summary": None,
        "recommendations": [],
    }

    save_workspace_artifacts(
        workspace_path=workspace,
        input_path=tmp_path / "one.sql",
        original_sql="SELECT 1;",
        obfuscated_sql="SELECT 1;",
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        llm_workflow_report_payload=llm_workflow_report,
    )
    assert (workspace / "reports" / "llm_workflow_report.json").exists()
    assert (workspace / "reports" / "llm_workflow_report.schema.json").exists()

    save_workspace_artifacts(
        workspace_path=workspace,
        input_path=tmp_path / "two.sql",
        original_sql="SELECT 2;",
        obfuscated_sql="SELECT 2;",
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        llm_workflow_report_payload=None,
    )
    assert (workspace / "reports" / "llm_workflow_report.json").exists() is False
    assert (workspace / "reports" / "llm_workflow_report.schema.json").exists() is False



def test_load_llm_workflow_report_valid(tmp_path: Path):
    report_path = tmp_path / "llm_workflow_report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "llm_safe_requested": True,
                "llm_safe_approved": False,
                "obfuscation_summary": {"statement_count": 2},
                "deobfuscation_summary": {"unknown_count": 0},
                "recommendations": ["review fallback-preserved statements"],
            }
        ),
        encoding="utf-8",
    )

    payload = load_llm_workflow_report(report_path)
    assert payload["llm_safe_requested"] is True
    assert payload["llm_safe_approved"] is False
    assert payload["obfuscation_summary"]["statement_count"] == 2



def test_load_llm_workflow_report_rejects_invalid_recommendations(tmp_path: Path):
    report_path = tmp_path / "llm_workflow_report.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "llm_safe_requested": True,
                "llm_safe_approved": True,
                "obfuscation_summary": {},
                "deobfuscation_summary": None,
                "recommendations": [123],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError, match="recommendations"):
        load_llm_workflow_report(report_path)



def test_save_workspace_artifacts_removes_stale_privacy_summary_report(tmp_path: Path):
    workspace = tmp_path / "sample.obf"
    mapping_payload = {
        "schema_version": 1,
        "entries": [],
        "forward_index": {},
        "reverse_index": {},
    }
    context_payload = {
        "schema_version": 1,
        "dialect": "tsql",
        "seed": None,
        "pretty": True,
        "redact_literals": False,
        "strip_comments": False,
        "redaction_mode": "none",
        "redaction_policy": "all",
        "sensitive_columns": [],
        "batch_count": 1,
        "statement_count": 1,
        "mapping_entry_count": 0,
    }
    privacy_summary = {
        "schema_version": 1,
        "dialect": "tsql",
        "statement_count": 1,
        "analyzed_statement_count": 1,
        "fallback_preserved_statement_count": 0,
        "llm_safe_blocked": False,
        "manual_review_recommended": False,
        "blocking_identifier_classes": [],
        "warning_identifier_classes": [],
        "identifier_surface": {
            "local_variables": {"occurrence_count": 0, "unique_count": 0, "examples": []},
            "system_variables": {"occurrence_count": 0, "unique_count": 0, "examples": []},
            "user_defined_functions": {"occurrence_count": 0, "unique_count": 0, "examples": []},
            "custom_schema_qualifiers": {"occurrence_count": 0, "unique_count": 0, "examples": []},
            "common_schema_qualifiers": {"occurrence_count": 0, "unique_count": 0, "examples": []},
            "catalog_qualifiers": {"occurrence_count": 0, "unique_count": 0, "examples": []},
        },
        "blockers": [],
        "warnings": [],
        "recommendations": [],
    }

    save_workspace_artifacts(
        workspace_path=workspace,
        input_path=tmp_path / "one.sql",
        original_sql="SELECT 1;",
        obfuscated_sql="SELECT 1;",
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        privacy_summary_payload=privacy_summary,
    )
    assert (workspace / "reports" / "privacy_summary.json").exists()
    assert (workspace / "reports" / "privacy_summary.schema.json").exists()

    save_workspace_artifacts(
        workspace_path=workspace,
        input_path=tmp_path / "two.sql",
        original_sql="SELECT 2;",
        obfuscated_sql="SELECT 2;",
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        privacy_summary_payload=None,
    )
    assert (workspace / "reports" / "privacy_summary.json").exists() is False
    assert (workspace / "reports" / "privacy_summary.schema.json").exists() is False



def test_load_privacy_summary_report_valid(tmp_path: Path):
    report_path = tmp_path / "privacy_summary.json"
    report_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dialect": "tsql",
                "statement_count": 2,
                "analyzed_statement_count": 2,
                "fallback_preserved_statement_count": 0,
                "llm_safe_blocked": True,
                "manual_review_recommended": True,
                "blocking_identifier_classes": ["local_variables"],
                "warning_identifier_classes": ["common_schema_qualifiers"],
                "identifier_surface": {
                    "local_variables": {"occurrence_count": 1, "unique_count": 1, "examples": ["@UserId"]},
                    "system_variables": {"occurrence_count": 0, "unique_count": 0, "examples": []},
                    "user_defined_functions": {"occurrence_count": 0, "unique_count": 0, "examples": []},
                    "custom_schema_qualifiers": {"occurrence_count": 0, "unique_count": 0, "examples": []},
                    "common_schema_qualifiers": {"occurrence_count": 1, "unique_count": 1, "examples": ["dbo"]},
                    "catalog_qualifiers": {"occurrence_count": 0, "unique_count": 0, "examples": []},
                },
                "blockers": ["1 local variable reference remains visible in obfuscated SQL: @UserId."],
                "warnings": ["1 common schema qualifier remains visible in obfuscated SQL: dbo."],
                "recommendations": ["review before sharing"],
            }
        ),
        encoding="utf-8",
    )

    payload = load_privacy_summary_report(report_path)
    assert payload["llm_safe_blocked"] is True
    assert payload["identifier_surface"]["local_variables"]["occurrence_count"] == 1
