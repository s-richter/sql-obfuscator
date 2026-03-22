from __future__ import annotations

import json

from pathlib import Path

import pytest

from sql_obfuscator.errors import WorkspaceError
from sql_obfuscator.workspace import (
    default_workspace_path,
    load_context_payload,
    load_llm_workflow_report,
    load_mapping_payload,
    load_redaction_payload,
    save_workspace_artifacts,
    save_translation_artifacts,
)


def test_default_workspace_path_uses_stem(tmp_path: Path):
    input_path = tmp_path / "sample.sql"
    workspace = default_workspace_path(input_path)
    assert workspace == tmp_path / "sample.obf"


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
