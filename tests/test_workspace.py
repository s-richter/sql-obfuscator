from __future__ import annotations

from pathlib import Path

import pytest

from sql_obfuscator.errors import WorkspaceError
from sql_obfuscator.workspace import (
    default_workspace_path,
    load_context_payload,
    load_mapping_payload,
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
