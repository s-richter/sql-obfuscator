from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError
from sqlglot.expressions import Expression

from .dialects_factory import get_dialect_profile
from .errors import ParseScriptError, WorkspaceError

ALLOWED_REDACTION_MODES = {"none", "irreversible", "reversible"}
ALLOWED_REDACTION_POLICIES = {"all", "strings-only", "sensitive"}
_STRING_PLACEHOLDER_PREFIX = "__SQL_OBFUSCATOR_STR_"
_STRING_PLACEHOLDER_SUFFIX = "__"
_NUMERIC_PLACEHOLDER_BASE = 900_000_000_000
_NUMERIC_PLACEHOLDER_RE = re.compile(r"^9\d{11}$")


@dataclass
class RedactionResult:
    output_sql: str
    redaction_payload: dict[str, Any] | None


def apply_redaction(
    script: str,
    *,
    dialect: str,
    pretty: bool,
    redact_literals: bool,
    strip_comments: bool,
    redaction_mode: str,
    redaction_policy: str = "all",
    sensitive_columns: set[str] | None = None,
) -> RedactionResult:
    if redaction_mode not in ALLOWED_REDACTION_MODES:
        raise WorkspaceError(f"Unsupported redaction mode: {redaction_mode}")
    if redaction_policy not in ALLOWED_REDACTION_POLICIES:
        raise WorkspaceError(f"Unsupported redaction policy: {redaction_policy}")
    if redaction_mode == "none":
        return RedactionResult(output_sql=script, redaction_payload=None)
    if not redact_literals and not strip_comments:
        return RedactionResult(output_sql=script, redaction_payload=None)

    profile = get_dialect_profile(dialect)
    batches = profile.split_batches(script)
    output_batches: list[str] = []
    literal_entries: list[dict[str, Any]] = []
    literal_index = 0

    def _next_literal_index() -> int:
        nonlocal literal_index
        literal_index += 1
        return literal_index

    for batch_index, batch_sql in enumerate(batches, start=1):
        if not batch_sql.strip():
            output_batches.append(batch_sql)
            continue
        try:
            statements = parse(batch_sql, dialect=dialect)
        except ParseError as exc:
            raise ParseScriptError(
                f"Parse error during redaction in batch {batch_index}/{len(batches)}: {exc}"
            ) from exc
        redacted = [
            _redact_statement(
                stmt,
                redact_literals=redact_literals,
                strip_comments=strip_comments,
                redaction_mode=redaction_mode,
                redaction_policy=redaction_policy,
                sensitive_columns=sensitive_columns or set(),
                literal_entries=literal_entries,
                next_index=_next_literal_index,
            )
            for stmt in statements
        ]
        output_batches.append(";\n".join(stmt.sql(dialect=dialect, pretty=pretty) for stmt in redacted))

    redaction_payload: dict[str, Any] | None = None
    if redaction_mode == "reversible" and literal_entries:
        redaction_payload = {
            "schema_version": 1,
            "mode": "reversible",
            "entries": literal_entries,
        }

    return RedactionResult(
        output_sql=profile.join_batches(output_batches),
        redaction_payload=redaction_payload,
    )


def _redact_statement(
    statement: Expression,
    *,
    redact_literals: bool,
    strip_comments: bool,
    redaction_mode: str,
    redaction_policy: str,
    sensitive_columns: set[str],
    literal_entries: list[dict[str, Any]],
    next_index,
) -> Expression:
    def _transform(node: Expression) -> Expression:
        if strip_comments and hasattr(node, "comments"):
            node.comments = None
        if redact_literals and isinstance(node, exp.Literal):
            if not _should_redact_literal(
                node,
                redaction_policy=redaction_policy,
                sensitive_columns=sensitive_columns,
            ):
                return node
            if redaction_mode == "irreversible":
                value = "<REDACTED_STR>" if node.is_string else "0"
                return exp.Literal(this=value, is_string=node.is_string)
            placeholder = _literal_placeholder(node.is_string, next_index())
            literal_entries.append(
                {
                    "placeholder": placeholder,
                    "original_this": node.this,
                    "is_string": node.is_string,
                }
            )
            value = placeholder
            return exp.Literal(this=value, is_string=node.is_string)
        return node

    return statement.transform(_transform, copy=True)


def _should_skip_literal_redaction(node: exp.Literal) -> bool:
    if node.is_string:
        return False
    # Keep structural datatype parameters unchanged, e.g. NUMERIC(10, 2).
    parent = node.parent
    while isinstance(parent, Expression):
        if isinstance(parent, (exp.DataTypeParam, exp.DataType)):
            return True
        parent = parent.parent
    return False


def _should_redact_literal(
    node: exp.Literal,
    *,
    redaction_policy: str,
    sensitive_columns: set[str],
) -> bool:
    if _should_skip_literal_redaction(node):
        return False
    if redaction_policy == "all":
        return True
    if redaction_policy == "strings-only":
        return node.is_string
    return _is_sensitive_literal_context(node, sensitive_columns)


def _is_sensitive_literal_context(node: exp.Literal, sensitive_columns: set[str]) -> bool:
    if not sensitive_columns:
        return False
    parent = node.parent
    while isinstance(parent, Expression):
        if isinstance(parent, (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Like, exp.ILike, exp.Between)):
            for identifier in parent.find_all(exp.Identifier):
                if identifier.name.lower() in sensitive_columns:
                    return True
        if isinstance(parent, exp.In):
            lhs = parent.args.get("this")
            if isinstance(lhs, exp.Column):
                col = lhs.this
                if isinstance(col, exp.Identifier) and col.name.lower() in sensitive_columns:
                    return True
        parent = parent.parent
    return False


def restore_reversible_redaction(
    script: str,
    *,
    dialect: str,
    pretty: bool,
    redaction_payload: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if redaction_payload.get("mode") != "reversible":
        raise WorkspaceError("Unsupported redaction payload mode for restoration.")

    entries = redaction_payload.get("entries", [])
    placeholder_map: dict[tuple[bool, str], dict[str, Any]] = {}
    expected_placeholders: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        placeholder = entry.get("placeholder")
        original_this = entry.get("original_this")
        is_string = entry.get("is_string")
        if not isinstance(placeholder, str) or not isinstance(original_this, str) or not isinstance(is_string, bool):
            continue
        expected_placeholders.add(placeholder)
        placeholder_map[(is_string, placeholder)] = entry

    profile = get_dialect_profile(dialect)
    batches = profile.split_batches(script)
    output_batches: list[str] = []
    restored_placeholders: set[str] = set()
    unknown_placeholders: list[str] = []

    for batch_index, batch_sql in enumerate(batches, start=1):
        if not batch_sql.strip():
            output_batches.append(batch_sql)
            continue
        try:
            statements = parse(batch_sql, dialect=dialect)
        except ParseError as exc:
            raise ParseScriptError(
                f"Parse error during reversible redaction restoration in batch {batch_index}/{len(batches)}: {exc}"
            ) from exc
        restored_statements = [
            _restore_statement_literals(
                stmt,
                placeholder_map=placeholder_map,
                restored_placeholders=restored_placeholders,
                unknown_placeholders=unknown_placeholders,
            )
            for stmt in statements
        ]
        output_batches.append(
            ";\n".join(stmt.sql(dialect=dialect, pretty=pretty) for stmt in restored_statements)
        )

    missing_placeholders = sorted(expected_placeholders - restored_placeholders)
    report = {
        "mode": "reversible",
        "expected_placeholders": len(expected_placeholders),
        "restored_placeholders": len(restored_placeholders),
        "unknown_placeholder_count": len(unknown_placeholders),
        "missing_placeholder_count": len(missing_placeholders),
        "unknown_placeholders": unknown_placeholders,
        "missing_placeholders": missing_placeholders,
    }
    return profile.join_batches(output_batches), report


def _restore_statement_literals(
    statement: Expression,
    *,
    placeholder_map: dict[tuple[bool, str], dict[str, Any]],
    restored_placeholders: set[str],
    unknown_placeholders: list[str],
) -> Expression:
    def _transform(node: Expression) -> Expression:
        if not isinstance(node, exp.Literal):
            return node
        if not _looks_like_placeholder(node):
            return node

        key = (node.is_string, str(node.this))
        entry = placeholder_map.get(key)
        if entry is None:
            unknown_placeholders.append(str(node.this))
            return node
        restored_placeholders.add(entry["placeholder"])
        return exp.Literal(this=entry["original_this"], is_string=entry["is_string"])

    return statement.transform(_transform, copy=True)


def _looks_like_placeholder(node: exp.Literal) -> bool:
    value = str(node.this)
    if node.is_string:
        return value.startswith(_STRING_PLACEHOLDER_PREFIX) and value.endswith(_STRING_PLACEHOLDER_SUFFIX)
    return _NUMERIC_PLACEHOLDER_RE.match(value) is not None


def _literal_placeholder(is_string: bool, index: int) -> str:
    if is_string:
        return f"{_STRING_PLACEHOLDER_PREFIX}{index:06d}{_STRING_PLACEHOLDER_SUFFIX}"
    return str(_NUMERIC_PLACEHOLDER_BASE + index)
