from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .errors import WorkspaceError


MAPPING_SCHEMA_VERSION = 1
CONTEXT_SCHEMA_VERSION = 1
INTEGRITY_SCHEMA_VERSION = 1

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

INTEGRITY_TRACKED_FILES = [
    "original.sql",
    "obfuscated.sql",
    "mapping.json",
    "context.json",
]


def default_workspace_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.obf")


def save_workspace_artifacts(
    *,
    workspace_path: Path,
    input_path: Path,
    original_sql: str,
    obfuscated_sql: str,
    mapping_payload: dict[str, Any],
    context_payload: dict[str, Any],
    llm_instructions_text: str | None = None,
) -> None:
    try:
        workspace_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorkspaceError(f"Unable to create workspace: {workspace_path}") from exc

    _write_text(workspace_path / "original.sql", original_sql)
    _write_text(workspace_path / "obfuscated.sql", obfuscated_sql)
    _write_text(
        workspace_path / "llm_instructions.md",
        llm_instructions_text
        if llm_instructions_text is not None
        else _default_llm_instructions(
            input_path=input_path,
            dialect=context_payload.get("dialect", "tsql"),
        ),
    )
    _write_json(workspace_path / "mapping.schema.json", MAPPING_JSON_SCHEMA)
    _write_json(workspace_path / "context.schema.json", CONTEXT_JSON_SCHEMA)
    _write_json(workspace_path / "integrity.schema.json", INTEGRITY_JSON_SCHEMA)

    context = dict(context_payload)
    context.update(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "input_file": str(input_path),
        }
    )
    _write_json(workspace_path / "mapping.json", mapping_payload)
    _write_json(workspace_path / "context.json", context)
    _write_json(workspace_path / "integrity.json", _build_integrity_payload(workspace_path))


def load_mapping_payload(mapping_path: Path) -> dict[str, Any]:
    payload = _read_json(mapping_path)
    _validate_mapping_payload(payload, source=mapping_path)
    return payload


def load_context_payload(context_path: Path) -> dict[str, Any]:
    payload = _read_json(context_path)
    _validate_context_payload(payload, source=context_path)
    return payload


def validate_workspace_integrity(workspace_path: Path) -> dict[str, Any]:
    integrity_path = workspace_path / "integrity.json"
    payload = _read_json(integrity_path)
    _validate_integrity_payload(payload, source=integrity_path)
    if payload.get("algorithm") != "sha256":
        raise WorkspaceError(
            f"Unsupported integrity algorithm in {integrity_path}: {payload.get('algorithm')}"
        )

    files = payload.get("files", {})
    for rel_path, expected_hash in files.items():
        if not isinstance(rel_path, str) or not isinstance(expected_hash, str):
            raise WorkspaceError(f"Invalid integrity entry in {integrity_path}: {rel_path}")
        target = workspace_path / rel_path
        if not target.exists():
            raise WorkspaceError(f"Integrity check failed: missing file {target}")
        actual_hash = _sha256_file(target)
        if actual_hash != expected_hash:
            raise WorkspaceError(
                "Integrity check failed: checksum mismatch for "
                f"{target}. Expected {expected_hash}, got {actual_hash}."
            )
    return payload


def save_deobfuscation_artifacts(
    *,
    workspace_path: Path,
    deobfuscated_sql: str,
    report_payload: dict[str, Any],
) -> None:
    reports_path = workspace_path / "reports"
    try:
        reports_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorkspaceError(f"Unable to create reports folder: {reports_path}") from exc

    _write_text(workspace_path / "deobfuscated.sql", deobfuscated_sql)
    _write_json(reports_path / "deobfuscation_report.json", report_payload)
    _write_text(
        reports_path / "coverage_report.txt",
        "\n".join(
            [
                f"mapped_identifiers: {report_payload.get('mapped_identifiers', 0)}",
                f"unknown_count: {report_payload.get('unknown_count', 0)}",
                f"ambiguous_count: {report_payload.get('ambiguous_count', 0)}",
                f"batch_count: {report_payload.get('batch_count', 0)}",
                f"statement_count: {report_payload.get('statement_count', 0)}",
                f"unknown_by_kind: {report_payload.get('unknown_by_kind', {})}",
                f"ambiguous_by_kind: {report_payload.get('ambiguous_by_kind', {})}",
                "recommendations:",
                *[
                    f"- {line}"
                    for line in report_payload.get("recommendations", [])
                    if isinstance(line, str)
                ],
            ]
        )
        + "\n",
    )


def save_roundtrip_reports(
    *,
    workspace_path: Path,
    report_payload: dict[str, Any],
    diff_text: str | None = None,
) -> None:
    reports_path = workspace_path / "reports"
    try:
        reports_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise WorkspaceError(f"Unable to create reports folder: {reports_path}") from exc

    _write_json(reports_path / "roundtrip_report.json", report_payload)
    if diff_text is not None:
        _write_text(reports_path / "roundtrip_diff.txt", diff_text)


def _write_text(path: Path, content: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise WorkspaceError(f"Unable to write workspace file: {path}") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise WorkspaceError(f"Unable to write workspace file: {path}") from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise WorkspaceError(f"Unable to read workspace file for hashing: {path}") from exc
    return digest.hexdigest()


def _build_integrity_payload(workspace_path: Path) -> dict[str, Any]:
    files: dict[str, str] = {}
    for rel_path in INTEGRITY_TRACKED_FILES:
        target = workspace_path / rel_path
        files[rel_path] = _sha256_file(target)
    return {
        "schema_version": INTEGRITY_SCHEMA_VERSION,
        "algorithm": "sha256",
        "files": files,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise WorkspaceError(f"Unable to read workspace file: {path}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"Invalid JSON in workspace file: {path}") from exc
    if not isinstance(payload, dict):
        raise WorkspaceError(f"JSON root must be an object in: {path}")
    return payload


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


def _default_llm_instructions(*, input_path: Path, dialect: str) -> str:
    return (
        "# LLM Instructions for Obfuscated SQL\n\n"
        "You are optimizing an obfuscated SQL script. "
        "The output will be de-obfuscated afterward.\n\n"
        "## Input Context\n"
        f"- Original input file: `{input_path.name}`\n"
        f"- SQL dialect: `{dialect}`\n\n"
        "## Requirements\n"
        "1. Keep obfuscated identifiers unchanged whenever possible.\n"
        "2. Do not invent new table/column names unless absolutely required.\n"
        "3. Keep alias structure stable where possible.\n"
        "4. Prefer structural/query-plan improvements over renaming.\n"
        "5. Preserve SQL semantics unless explicitly asked to change behavior.\n\n"
        "## If new identifiers are unavoidable\n"
        "- Minimize the number of new identifiers.\n"
        "- Keep new identifiers syntactically valid for the dialect.\n"
        "- Clearly comment where and why new identifiers were introduced.\n"
    )
