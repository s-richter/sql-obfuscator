from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import WorkspaceError
from .llm_instructions import build_default_llm_instructions as _build_default_llm_instructions


MAPPING_SCHEMA_VERSION = 1
CONTEXT_SCHEMA_VERSION = 1
INTEGRITY_SCHEMA_VERSION = 1
REDACTION_SCHEMA_VERSION = 1
LLM_WORKFLOW_REPORT_SCHEMA_VERSION = 1
PRIVACY_SUMMARY_REPORT_SCHEMA_VERSION = 1

MAPPING_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SQL Obfuscator Mapping Schema",
    "type": "object",
    "required": [
        "schema_version",
        "entries",
        "forward_index",
        "reverse_index",
    ],
}

CONTEXT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SQL Obfuscator Context Schema",
    "type": "object",
    "required": [
        "schema_version",
        "input_file",
        "dialect",
        "pretty",
        "batch_count",
        "statement_count",
        "mapping_entry_count",
    ],
}

INTEGRITY_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SQL Obfuscator Integrity Schema",
    "type": "object",
    "required": [
        "schema_version",
        "algorithm",
        "files",
    ],
}

TRANSLATION_REPORT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SQL Translation Report Schema",
    "type": "object",
    "required": [
        "source_dialect",
        "target_dialect",
        "batch_count",
        "statement_count",
        "translated_statement_count",
        "failed_statement_count",
        "warnings",
        "failures",
        "validated",
    ],
}

REDACTION_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SQL Redaction Metadata Schema",
    "type": "object",
    "required": [
        "schema_version",
        "mode",
        "entries",
    ],
}

LLM_WORKFLOW_REPORT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SQL LLM Workflow Report Schema",
    "type": "object",
    "required": [
        "schema_version",
        "llm_safe_requested",
        "llm_safe_approved",
        "obfuscation_summary",
        "deobfuscation_summary",
    ],
}

LLM_EDIT_APPLICATION_REPORT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SQL LLM Edit Application Report Schema",
    "type": "object",
    "required": [
        "schema_version",
        "format",
        "applied_edit_count",
        "untouched_statement_count",
        "statement_count",
        "targeted_statement_ids",
    ],
}

PRIVACY_SUMMARY_REPORT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "SQL Privacy Summary Report Schema",
    "type": "object",
    "required": [
        "schema_version",
        "dialect",
        "statement_count",
        "analyzed_statement_count",
        "fallback_preserved_statement_count",
        "llm_safe_blocked",
        "manual_review_recommended",
        "blocking_identifier_classes",
        "warning_identifier_classes",
        "identifier_surface",
        "blockers",
        "warnings",
        "recommendations",
    ],
}

INTEGRITY_TRACKED_FILES = [
    "original.sql",
    "obfuscated.sql",
    "mapping.json",
    "context.json",
]


@dataclass(frozen=True)
class WorkspaceSnapshot:
    obfuscated_sql: str
    mapping_payload: dict[str, Any]
    context_payload: dict[str, Any]
    redaction_payload: dict[str, Any] | None
    privacy_summary: dict[str, Any]
    llm_workflow_report: dict[str, Any]


def _local_workspace_store():
    from .local_workspace_store import LocalWorkspaceStore

    return LocalWorkspaceStore()


def default_workspace_path(input_path: Path) -> Path:
    return _local_workspace_store().default_workspace_path(input_path)


def save_workspace_snapshot(
    *,
    workspace_path: Path,
    input_path: Path,
    original_sql: str,
    snapshot: WorkspaceSnapshot,
    instructions_text: str | None = None,
) -> None:
    _local_workspace_store().save_workspace_snapshot(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=original_sql,
        snapshot=snapshot,
        instructions_text=instructions_text,
    )


def load_workspace_snapshot(workspace_path: Path) -> WorkspaceSnapshot:
    return _local_workspace_store().load_workspace_snapshot(workspace_path)


def save_workspace_artifacts(
    *,
    workspace_path: Path,
    input_path: Path,
    original_sql: str,
    obfuscated_sql: str,
    mapping_payload: dict[str, Any],
    context_payload: dict[str, Any],
    llm_instructions_text: str | None = None,
    redaction_payload: dict[str, Any] | None = None,
    llm_workflow_report_payload: dict[str, Any] | None = None,
    privacy_summary_payload: dict[str, Any] | None = None,
) -> None:
    _local_workspace_store().save_workspace_artifacts(
        workspace_path=workspace_path,
        input_path=input_path,
        original_sql=original_sql,
        obfuscated_sql=obfuscated_sql,
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        llm_instructions_text=llm_instructions_text,
        redaction_payload=redaction_payload,
        llm_workflow_report_payload=llm_workflow_report_payload,
        privacy_summary_payload=privacy_summary_payload,
    )


def load_mapping_payload(mapping_path: Path) -> dict[str, Any]:
    return _local_workspace_store().load_mapping_payload(mapping_path)


def load_context_payload(context_path: Path) -> dict[str, Any]:
    return _local_workspace_store().load_context_payload(context_path)


def load_redaction_payload(redaction_path: Path) -> dict[str, Any]:
    return _local_workspace_store().load_redaction_payload(redaction_path)


def load_llm_workflow_report(report_path: Path) -> dict[str, Any]:
    return _local_workspace_store().load_llm_workflow_report(report_path)


def load_privacy_summary_report(report_path: Path) -> dict[str, Any]:
    return _local_workspace_store().load_privacy_summary_report(report_path)


def validate_workspace_integrity(workspace_path: Path) -> dict[str, Any]:
    return _local_workspace_store().validate_workspace_integrity(workspace_path)


def save_deobfuscation_artifacts(
    *,
    workspace_path: Path,
    deobfuscated_sql: str,
    report_payload: dict[str, Any],
) -> None:
    _local_workspace_store().save_deobfuscation_artifacts(
        workspace_path=workspace_path,
        deobfuscated_sql=deobfuscated_sql,
        report_payload=report_payload,
    )


def save_roundtrip_reports(
    *,
    workspace_path: Path,
    report_payload: dict[str, Any],
    diff_text: str | None = None,
    original_pretty_sql: str | None = None,
    deobfuscated_pretty_sql: str | None = None,
    normalized_diff_text: str | None = None,
) -> None:
    _local_workspace_store().save_roundtrip_reports(
        workspace_path=workspace_path,
        report_payload=report_payload,
        diff_text=diff_text,
        original_pretty_sql=original_pretty_sql,
        deobfuscated_pretty_sql=deobfuscated_pretty_sql,
        normalized_diff_text=normalized_diff_text,
    )


def save_translation_artifacts(
    *,
    workspace_path: Path,
    report_payload: dict[str, Any],
    translated_sql: str | None = None,
) -> None:
    _local_workspace_store().save_translation_artifacts(
        workspace_path=workspace_path,
        report_payload=report_payload,
        translated_sql=translated_sql,
    )


def save_llm_workflow_report(
    *,
    workspace_path: Path,
    report_payload: dict[str, Any],
) -> None:
    _local_workspace_store().save_llm_workflow_report(
        workspace_path=workspace_path,
        report_payload=report_payload,
    )


def save_llm_workflow_report_if_present(
    *,
    workspace_path: Path,
    report_payload: dict[str, Any],
) -> None:
    _local_workspace_store().save_llm_workflow_report_if_present(
        workspace_path=workspace_path,
        report_payload=report_payload,
    )


def save_llm_edit_application_report(
    *,
    workspace_path: Path,
    report_payload: dict[str, Any],
) -> None:
    _local_workspace_store().save_llm_edit_application_report(
        workspace_path=workspace_path,
        report_payload=report_payload,
    )


def save_privacy_summary_report(
    *,
    workspace_path: Path,
    report_payload: dict[str, Any],
) -> None:
    _local_workspace_store().save_privacy_summary_report(
        workspace_path=workspace_path,
        report_payload=report_payload,
    )


def _validate_mapping_payload(payload: dict[str, Any], *, source: Path) -> None:
    if payload.get("schema_version") != MAPPING_SCHEMA_VERSION:
        raise WorkspaceError(
            f"Unsupported mapping schema in {source}: {payload.get('schema_version')}"
        )
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise WorkspaceError(f"mapping.json missing list field 'entries': {source}")
    forward_index = payload.get("forward_index")
    if not isinstance(forward_index, dict):
        raise WorkspaceError(f"mapping.json missing object field 'forward_index': {source}")
    reverse_index = payload.get("reverse_index")
    if not isinstance(reverse_index, dict):
        raise WorkspaceError(f"mapping.json missing object field 'reverse_index': {source}")

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise WorkspaceError(f"mapping entry at index {idx} is not an object in {source}")
        for field in (
            "normalized_original",
            "temp_prefix",
            "original_lexeme",
            "original_unbracketed",
            "obfuscated_unbracketed",
            "obfuscated_lexeme",
        ):
            if not isinstance(entry.get(field), str):
                raise WorkspaceError(
                    f"mapping entry {idx} missing/invalid field '{field}' in {source}"
                )
        if not isinstance(entry.get("original_was_bracketed"), bool):
            raise WorkspaceError(
                f"mapping entry {idx} missing/invalid field 'original_was_bracketed' in {source}"
            )
        occurrences = entry.get("occurrences")
        if not isinstance(occurrences, list):
            raise WorkspaceError(
                f"mapping entry {idx} missing/invalid list field 'occurrences' in {source}"
            )
        for occ_idx, occurrence in enumerate(occurrences):
            if not isinstance(occurrence, dict):
                raise WorkspaceError(
                    f"occurrence {occ_idx} in mapping entry {idx} is not an object in {source}"
                )
            for field in ("kind", "scope_id", "parent_kind", "role"):
                if not isinstance(occurrence.get(field), str):
                    raise WorkspaceError(
                        f"occurrence {occ_idx} in mapping entry {idx} missing/invalid "
                        f"field '{field}' in {source}"
                    )
            for field in ("batch_index", "statement_index"):
                if not isinstance(occurrence.get(field), int):
                    raise WorkspaceError(
                        f"occurrence {occ_idx} in mapping entry {idx} missing/invalid "
                        f"field '{field}' in {source}"
                    )
            type_lexeme = occurrence.get("type_lexeme")
            if type_lexeme is not None and not isinstance(type_lexeme, str):
                raise WorkspaceError(
                    f"occurrence {occ_idx} in mapping entry {idx} has invalid "
                    f"field 'type_lexeme' in {source}"
                )
            for field in ("statement_kind", "clause_kind", "node_kind", "arg_key"):
                value = occurrence.get(field)
                if value is not None and not isinstance(value, str):
                    raise WorkspaceError(
                        f"occurrence {occ_idx} in mapping entry {idx} has invalid "
                        f"field '{field}' in {source}"
                    )

    for key, value in forward_index.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise WorkspaceError(
                f"mapping.json has invalid forward_index entry '{key}' in {source}"
            )
    for key, value in reverse_index.items():
        if not isinstance(key, str) or not isinstance(value, dict):
            raise WorkspaceError(
                f"mapping.json has invalid reverse_index entry '{key}' in {source}"
            )
        if not isinstance(value.get("normalized_original"), str):
            raise WorkspaceError(
                f"reverse_index entry '{key}' missing/invalid normalized_original in {source}"
            )
        if not isinstance(value.get("temp_prefix"), str):
            raise WorkspaceError(
                f"reverse_index entry '{key}' missing/invalid temp_prefix in {source}"
            )


def _validate_context_payload(payload: dict[str, Any], *, source: Path) -> None:
    if payload.get("schema_version") != CONTEXT_SCHEMA_VERSION:
        raise WorkspaceError(
            f"Unsupported context schema in {source}: {payload.get('schema_version')}"
        )
    required_types = {
        "input_file": str,
        "dialect": str,
        "pretty": bool,
        "batch_count": int,
        "statement_count": int,
        "mapping_entry_count": int,
    }
    for field, expected_type in required_types.items():
        if not isinstance(payload.get(field), expected_type):
            raise WorkspaceError(
                f"context.json missing/invalid field '{field}' in {source}"
            )
    # seed is optional but must be int or null
    seed = payload.get("seed")
    if seed is not None and not isinstance(seed, int):
        raise WorkspaceError(f"context.json has invalid 'seed' in {source}")
    optional_types = {
        "redact_literals": bool,
        "strip_comments": bool,
        "redaction_mode": str,
        "redaction_policy": str,
    }
    for field, expected_type in optional_types.items():
        value = payload.get(field)
        if value is not None and not isinstance(value, expected_type):
            raise WorkspaceError(f"context.json has invalid '{field}' in {source}")
    sensitive_columns = payload.get("sensitive_columns")
    if sensitive_columns is not None:
        if not isinstance(sensitive_columns, list):
            raise WorkspaceError(f"context.json has invalid 'sensitive_columns' in {source}")
        if any(not isinstance(item, str) for item in sensitive_columns):
            raise WorkspaceError(f"context.json has invalid 'sensitive_columns' in {source}")
    statement_anchors = payload.get("statement_anchors")
    if statement_anchors is not None:
        if not isinstance(statement_anchors, list):
            raise WorkspaceError(f"context.json has invalid 'statement_anchors' in {source}")
        for idx, anchor in enumerate(statement_anchors):
            if not isinstance(anchor, dict):
                raise WorkspaceError(
                    f"context.json has invalid statement anchor at index {idx} in {source}"
                )
            required_fields = {
                "statement_id": str,
                "batch_index": int,
                "statement_index": int,
                "global_statement_index": int,
                "statement_kind": str,
                "fingerprint": str,
                "fallback_preserved": bool,
                "preview": str,
            }
            for field, expected_type in required_fields.items():
                if not isinstance(anchor.get(field), expected_type):
                    raise WorkspaceError(
                        f"context.json has invalid statement anchor field '{field}' at index {idx} in {source}"
                    )
            for field in ("identifier_tokens", "placeholder_tokens"):
                value = anchor.get(field)
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    raise WorkspaceError(
                        f"context.json has invalid statement anchor field '{field}' at index {idx} in {source}"
                    )
            obfuscated_sql = anchor.get("obfuscated_sql")
            if obfuscated_sql is not None and not isinstance(obfuscated_sql, str):
                raise WorkspaceError(
                    f"context.json has invalid statement anchor field 'obfuscated_sql' at index {idx} in {source}"
                )


def _validate_integrity_payload(payload: dict[str, Any], *, source: Path) -> None:
    if payload.get("schema_version") != INTEGRITY_SCHEMA_VERSION:
        raise WorkspaceError(
            f"Unsupported integrity schema in {source}: {payload.get('schema_version')}"
        )
    if not isinstance(payload.get("algorithm"), str):
        raise WorkspaceError(f"integrity.json missing/invalid field 'algorithm' in {source}")
    files = payload.get("files")
    if not isinstance(files, dict):
        raise WorkspaceError(f"integrity.json missing/invalid field 'files' in {source}")


def _validate_redaction_payload(payload: dict[str, Any], *, source: Path) -> None:
    if payload.get("schema_version") != REDACTION_SCHEMA_VERSION:
        raise WorkspaceError(
            f"Unsupported redaction schema in {source}: {payload.get('schema_version')}"
        )
    if payload.get("mode") != "reversible":
        raise WorkspaceError(f"Unsupported redaction mode in {source}: {payload.get('mode')}")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise WorkspaceError(f"redaction.json missing/invalid list field 'entries' in {source}")
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise WorkspaceError(f"redaction entry at index {idx} is not an object in {source}")
        if not isinstance(entry.get("placeholder"), str):
            raise WorkspaceError(
                f"redaction entry {idx} missing/invalid field 'placeholder' in {source}"
            )
        if not isinstance(entry.get("original_this"), str):
            raise WorkspaceError(
                f"redaction entry {idx} missing/invalid field 'original_this' in {source}"
            )
        if not isinstance(entry.get("is_string"), bool):
            raise WorkspaceError(
                f"redaction entry {idx} missing/invalid field 'is_string' in {source}"
            )


def _validate_llm_workflow_report_payload(payload: dict[str, Any], *, source: Path) -> None:
    if payload.get("schema_version") != LLM_WORKFLOW_REPORT_SCHEMA_VERSION:
        raise WorkspaceError(
            f"Unsupported LLM workflow report schema in {source}: {payload.get('schema_version')}"
        )
    for field in ("llm_safe_requested", "llm_safe_approved"):
        if not isinstance(payload.get(field), bool):
            raise WorkspaceError(
                f"llm_workflow_report.json missing/invalid field '{field}' in {source}"
            )
    obfuscation_summary = payload.get("obfuscation_summary")
    if not isinstance(obfuscation_summary, dict):
        raise WorkspaceError(
            f"llm_workflow_report.json missing/invalid field 'obfuscation_summary' in {source}"
        )
    deobfuscation_summary = payload.get("deobfuscation_summary")
    if deobfuscation_summary is not None and not isinstance(deobfuscation_summary, dict):
        raise WorkspaceError(
            f"llm_workflow_report.json has invalid field 'deobfuscation_summary' in {source}"
        )
    recommendations = payload.get("recommendations")
    if recommendations is not None:
        if not isinstance(recommendations, list) or any(
            not isinstance(item, str) for item in recommendations
        ):
            raise WorkspaceError(
                f"llm_workflow_report.json has invalid field 'recommendations' in {source}"
            )


def _validate_privacy_summary_report_payload(payload: dict[str, Any], *, source: Path) -> None:
    if payload.get("schema_version") != PRIVACY_SUMMARY_REPORT_SCHEMA_VERSION:
        raise WorkspaceError(
            f"Unsupported privacy summary schema in {source}: {payload.get('schema_version')}"
        )
    if not isinstance(payload.get("dialect"), str):
        raise WorkspaceError(f"privacy_summary.json missing/invalid field 'dialect' in {source}")
    for field in ("statement_count", "analyzed_statement_count", "fallback_preserved_statement_count"):
        if not isinstance(payload.get(field), int):
            raise WorkspaceError(
                f"privacy_summary.json missing/invalid field '{field}' in {source}"
            )
    for field in ("llm_safe_blocked", "manual_review_recommended"):
        if not isinstance(payload.get(field), bool):
            raise WorkspaceError(
                f"privacy_summary.json missing/invalid field '{field}' in {source}"
            )
    for field in ("blocking_identifier_classes", "warning_identifier_classes", "blockers", "warnings", "recommendations"):
        value = payload.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise WorkspaceError(
                f"privacy_summary.json has invalid field '{field}' in {source}"
            )
    identifier_surface = payload.get("identifier_surface")
    if not isinstance(identifier_surface, dict):
        raise WorkspaceError(
            f"privacy_summary.json missing/invalid field 'identifier_surface' in {source}"
        )
    expected_keys = (
        "local_variables",
        "system_variables",
        "user_defined_functions",
        "custom_schema_qualifiers",
        "common_schema_qualifiers",
        "catalog_qualifiers",
    )
    for key in expected_keys:
        bucket = identifier_surface.get(key)
        if not isinstance(bucket, dict):
            raise WorkspaceError(
                f"privacy_summary.json has invalid identifier surface bucket '{key}' in {source}"
            )
        if not isinstance(bucket.get("occurrence_count"), int) or not isinstance(bucket.get("unique_count"), int):
            raise WorkspaceError(
                f"privacy_summary.json has invalid counts for identifier surface bucket '{key}' in {source}"
            )
        examples = bucket.get("examples")
        if not isinstance(examples, list) or any(not isinstance(item, str) for item in examples):
            raise WorkspaceError(
                f"privacy_summary.json has invalid examples for identifier surface bucket '{key}' in {source}"
            )


def build_default_llm_instructions(
    *,
    input_name: str,
    dialect: str,
    statement_anchors: list[dict[str, Any]] | None = None,
) -> str:
    return _build_default_llm_instructions(
        input_name=input_name,
        dialect=dialect,
        statement_anchors=statement_anchors,
    )
