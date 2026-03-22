from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlglot.errors import ParseError

from .dialects_factory import get_dialect_profile
from .errors import WorkspaceError
from .sqlglot_compat import join_emitted_statements, parse_sql

LLM_EDITS_SCHEMA_VERSION = 1
LLM_EDITS_FORMAT = "statement_replacements"
_FENCED_JSON_RE = re.compile(r"^```(?:json)?\s*(?P<body>[\s\S]*?)\s*```$", re.IGNORECASE)


def llm_edits_example_json(*, statement_id: str = "stmt_0001") -> str:
    return json.dumps(
        {
            "schema_version": LLM_EDITS_SCHEMA_VERSION,
            "format": LLM_EDITS_FORMAT,
            "edits": [
                {
                    "statement_id": statement_id,
                    "sql": "SELECT ...",
                }
            ],
        },
        indent=2,
    )



def load_llm_edits_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise WorkspaceError(f"LLM edits file not found: {path}")
    if not path.is_file():
        raise WorkspaceError(f"LLM edits path is not a file: {path}")
    try:
        return parse_llm_edits_text(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorkspaceError(f"Unable to read LLM edits file: {path}") from exc



def parse_llm_edits_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise WorkspaceError("LLM edits file is empty.")
    fenced_match = _FENCED_JSON_RE.match(stripped)
    if fenced_match:
        stripped = fenced_match.group("body").strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise WorkspaceError(
            "LLM edits file is not valid JSON. Use raw JSON or a fenced ```json``` block."
        ) from exc
    if not isinstance(payload, dict):
        raise WorkspaceError("LLM edits payload must be a JSON object.")
    return payload



def apply_llm_statement_replacements(
    *,
    obfuscated_sql: str,
    statement_anchors: list[dict[str, Any]] | None,
    batch_count: int,
    dialect: str,
    edits_payload: dict[str, Any],
    statement_count: int | None = None,
) -> tuple[str, dict[str, Any]]:
    anchors = _validate_statement_anchors(statement_anchors, batch_count=batch_count, statement_count=statement_count)
    reconstructed = _reconstruct_script(anchors=anchors, batch_count=batch_count, dialect=dialect, edit_sql_by_id={})
    if reconstructed != obfuscated_sql:
        raise WorkspaceError(
            "Workspace statement anchors do not reconstruct obfuscated.sql exactly. "
            "Re-obfuscate the workspace with the current version before apply-llm-edits."
        )

    validated_payload = _validate_llm_edits_payload(
        edits_payload,
        known_statement_ids={anchor["statement_id"] for anchor in anchors},
        dialect=dialect,
    )
    edits = validated_payload["edits"]
    edit_sql_by_id = {edit["statement_id"]: edit["sql"] for edit in edits}
    output_sql = _reconstruct_script(
        anchors=anchors,
        batch_count=batch_count,
        dialect=dialect,
        edit_sql_by_id=edit_sql_by_id,
    )
    report = {
        "schema_version": 1,
        "format": validated_payload["format"],
        "applied_edit_count": len(edits),
        "untouched_statement_count": max(0, len(anchors) - len(edits)),
        "statement_count": len(anchors),
        "targeted_statement_ids": [edit["statement_id"] for edit in edits],
    }
    return output_sql, report



def _validate_statement_anchors(
    statement_anchors: list[dict[str, Any]] | None,
    *,
    batch_count: int,
    statement_count: int | None,
) -> list[dict[str, Any]]:
    if not isinstance(statement_anchors, list) or not statement_anchors:
        raise WorkspaceError(
            "Workspace context does not include statement anchors. Re-obfuscate with the current version before apply-llm-edits."
        )
    anchors: list[dict[str, Any]] = []
    seen_statement_ids: set[str] = set()
    seen_positions: set[tuple[int, int]] = set()
    for idx, anchor in enumerate(statement_anchors):
        if not isinstance(anchor, dict):
            raise WorkspaceError(f"Workspace statement anchor at index {idx} is invalid.")
        statement_id = anchor.get("statement_id")
        batch_index = anchor.get("batch_index")
        statement_index = anchor.get("statement_index")
        statement_sql = anchor.get("obfuscated_sql")
        if not isinstance(statement_id, str) or not statement_id:
            raise WorkspaceError(f"Workspace statement anchor at index {idx} is missing 'statement_id'.")
        if not isinstance(batch_index, int) or batch_index < 1 or batch_index > batch_count:
            raise WorkspaceError(
                f"Workspace statement anchor '{statement_id}' has invalid 'batch_index'."
            )
        if not isinstance(statement_index, int) or statement_index < 1:
            raise WorkspaceError(
                f"Workspace statement anchor '{statement_id}' has invalid 'statement_index'."
            )
        if not isinstance(statement_sql, str) or not statement_sql.strip():
            raise WorkspaceError(
                "Workspace statement anchors do not include exact per-statement obfuscated SQL. "
                "Re-obfuscate with the current version before apply-llm-edits."
            )
        if statement_id in seen_statement_ids:
            raise WorkspaceError(f"Workspace statement anchor '{statement_id}' is duplicated.")
        position = (batch_index, statement_index)
        if position in seen_positions:
            raise WorkspaceError(
                f"Workspace statement anchors contain duplicate position batch {batch_index}, statement {statement_index}."
            )
        seen_statement_ids.add(statement_id)
        seen_positions.add(position)
        anchors.append(anchor)
    anchors.sort(key=lambda item: (int(item["batch_index"]), int(item["statement_index"])))
    if statement_count is not None and len(anchors) != statement_count:
        raise WorkspaceError(
            "Workspace statement anchors do not match statement_count. "
            "Re-obfuscate with the current version before apply-llm-edits."
        )
    return anchors



def _validate_llm_edits_payload(
    payload: dict[str, Any],
    *,
    known_statement_ids: set[str],
    dialect: str,
) -> dict[str, Any]:
    if payload.get("schema_version") != LLM_EDITS_SCHEMA_VERSION:
        raise WorkspaceError(
            f"Unsupported LLM edits schema version: {payload.get('schema_version')}"
        )
    if payload.get("format") != LLM_EDITS_FORMAT:
        raise WorkspaceError(
            f"Unsupported LLM edits format: {payload.get('format')}"
        )
    edits = payload.get("edits")
    if not isinstance(edits, list):
        raise WorkspaceError("LLM edits payload must contain an 'edits' list.")

    validated_edits: list[dict[str, str]] = []
    seen_statement_ids: set[str] = set()
    for idx, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise WorkspaceError(f"LLM edit at index {idx} must be an object.")
        statement_id = edit.get("statement_id")
        sql = edit.get("sql")
        if not isinstance(statement_id, str) or not statement_id:
            raise WorkspaceError(f"LLM edit at index {idx} is missing 'statement_id'.")
        if statement_id in seen_statement_ids:
            raise WorkspaceError(f"LLM edits payload contains duplicate statement_id: {statement_id}")
        if statement_id not in known_statement_ids:
            raise WorkspaceError(f"LLM edits payload references unknown statement_id: {statement_id}")
        if not isinstance(sql, str) or not sql.strip():
            raise WorkspaceError(f"LLM edit '{statement_id}' is missing 'sql'.")
        _validate_replacement_sql(statement_id=statement_id, sql=sql, dialect=dialect)
        seen_statement_ids.add(statement_id)
        validated_edits.append({"statement_id": statement_id, "sql": sql})
    return {
        "schema_version": LLM_EDITS_SCHEMA_VERSION,
        "format": LLM_EDITS_FORMAT,
        "edits": validated_edits,
    }



def _validate_replacement_sql(*, statement_id: str, sql: str, dialect: str) -> None:
    profile = get_dialect_profile(dialect)
    non_empty_batches = [batch for batch in profile.split_batches(sql) if batch.strip()]
    if len(non_empty_batches) != 1:
        raise WorkspaceError(
            f"Edit '{statement_id}' must contain exactly one statement without GO batch separators."
        )
    try:
        statements = parse_sql(non_empty_batches[0], dialect=dialect)
    except ParseError as exc:
        raise WorkspaceError(f"Edit '{statement_id}' is not valid {dialect} SQL: {exc}") from exc
    if len(statements) != 1:
        raise WorkspaceError(
            f"Edit '{statement_id}' must contain exactly one SQL statement."
        )



def _reconstruct_script(
    *,
    anchors: list[dict[str, Any]],
    batch_count: int,
    dialect: str,
    edit_sql_by_id: dict[str, str],
) -> str:
    profile = get_dialect_profile(dialect)
    statements_by_batch: dict[int, list[tuple[int, str]]] = {batch_index: [] for batch_index in range(1, batch_count + 1)}
    for anchor in anchors:
        batch_index = int(anchor["batch_index"])
        statement_index = int(anchor["statement_index"])
        statement_id = str(anchor["statement_id"])
        statement_sql = edit_sql_by_id.get(statement_id, str(anchor["obfuscated_sql"]))
        statements_by_batch.setdefault(batch_index, []).append((statement_index, statement_sql))

    batches: list[str] = []
    for batch_index in range(1, batch_count + 1):
        statements = [sql for _, sql in sorted(statements_by_batch.get(batch_index, []), key=lambda item: item[0])]
        batches.append(join_emitted_statements(statements))
    return profile.join_batches(batches)
