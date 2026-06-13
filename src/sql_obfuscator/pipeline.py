from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlglot.errors import ParseError

from .dialects_base import DialectProfile
from .dialects_factory import get_dialect_profile
from .errors import ParseScriptError
from .names import IdentifierVocabulary
from .privacy import build_privacy_summary
from .redaction import apply_redaction
from .registry import IdentifierRegistry
from .sqlglot_compat import emit_sql, join_emitted_statements, parse_sql
from .statement_anchors import anchor_to_payload, build_statement_anchor
from .transformer import transform_statements

_GO_STANDALONE_RE = re.compile(r"^\s*GO\s*$", re.IGNORECASE)
_GO_PREFIX_RE = re.compile(r"^\s*GO\b", re.IGNORECASE)


@dataclass
class _ProcessedBatch:
    output_sql: str
    statement_count: int
    fallback_preserved_statement_count: int
    statement_anchors: list[dict[str, Any]]


def _extract_context_snippet(sql: str, max_length: int = 100) -> str:
    """Extract a snippet of SQL for error context."""
    snippet = sql.strip()
    if len(snippet) > max_length:
        snippet = snippet[:max_length] + "..."
    return snippet


def _format_parse_error(
    error: ParseError,
    batch_sql: str,
    batch_number: int,
    total_batches: int,
) -> str:
    """Format a parse error with context."""
    lines = [
        f"Parse error in batch {batch_number}/{total_batches}:",
        f"  Error: {error}",
    ]

    # Add SQL snippet for context
    snippet = _extract_context_snippet(batch_sql)
    lines.append(f"  SQL: {snippet}")

    return "\n".join(lines)


def _process_batch(
    batch_sql: str,
    *,
    dialect: str,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    pretty: bool = False,
    batch_number: int = 1,
    total_batches: int = 1,
    statement_start_index: int = 1,
    obfuscate_qualifiers: bool = False,
) -> _ProcessedBatch:
    if not batch_sql.strip():
        return _ProcessedBatch(
            output_sql=batch_sql,
            statement_count=0,
            fallback_preserved_statement_count=0,
            statement_anchors=[],
        )

    try:
        statements = parse_sql(batch_sql, dialect=dialect)
    except ParseError as exc:
        error_msg = _format_parse_error(exc, batch_sql, batch_number, total_batches)
        raise ParseScriptError(error_msg) from exc

    fallback_preserved_statement_count = sum(
        1 for statement in statements if isinstance(statement.meta.get("raw_sql"), str)
    )
    transformed = transform_statements(
        statements,
        registry=registry,
        batch_index=batch_number,
        batch_sql=batch_sql,
        dialect=dialect,
        profile=profile,
        obfuscate_qualifiers=obfuscate_qualifiers,
    )
    statement_sqls: list[str] = []
    statement_anchors: list[dict[str, Any]] = []
    for local_statement_index, statement in enumerate(transformed, start=1):
        statement_sql = emit_sql(statement, dialect=dialect, pretty=pretty)
        statement_sqls.append(statement_sql)
        anchor_payload = anchor_to_payload(
            build_statement_anchor(
                statement,
                dialect=dialect,
                batch_index=batch_number,
                statement_index=local_statement_index,
                global_statement_index=statement_start_index + local_statement_index - 1,
            )
        )
        anchor_payload["obfuscated_sql"] = statement_sql
        statement_anchors.append(anchor_payload)
    return _ProcessedBatch(
        output_sql=join_emitted_statements(statement_sqls),
        statement_count=len(statements),
        fallback_preserved_statement_count=fallback_preserved_statement_count,
        statement_anchors=statement_anchors,
    )


def _validate_strict_go(script: str, *, dialect: str) -> None:
    if dialect.lower() != "tsql":
        return
    for line_number, line in enumerate(script.splitlines(), start=1):
        if _GO_PREFIX_RE.match(line) and not _GO_STANDALONE_RE.match(line):
            snippet = line.strip()[:100]
            raise ParseScriptError(
                "Strict GO validation failed: unsupported batch separator form at "
                f"line {line_number}: {snippet!r}. Use standalone 'GO' on its own line."
            )


@dataclass
class ObfuscationResult:
    output_sql: str
    mapping_payload: dict
    context_payload: dict
    redaction_payload: dict | None = None
    obfuscation_report: dict[str, Any] | None = None
    privacy_summary: dict[str, Any] | None = None


def obfuscate_sql(
    script: str,
    *,
    dialect: str = "tsql",
    seed: int | None = None,
    strict_go: bool = False,
    pretty: bool = True,
    redact_literals: bool = False,
    strip_comments: bool = False,
    redaction_mode: str = "none",
    redaction_policy: str = "all",
    sensitive_columns: set[str] | None = None,
    identifier_vocabulary: IdentifierVocabulary | None = None,
    obfuscate_qualifiers: bool = False,
) -> str:
    result = obfuscate_sql_with_metadata(
        script,
        dialect=dialect,
        seed=seed,
        strict_go=strict_go,
        pretty=pretty,
        redact_literals=redact_literals,
        strip_comments=strip_comments,
        redaction_mode=redaction_mode,
        redaction_policy=redaction_policy,
        sensitive_columns=sensitive_columns,
        identifier_vocabulary=identifier_vocabulary,
        obfuscate_qualifiers=obfuscate_qualifiers,
    )
    return result.output_sql


def obfuscate_sql_with_metadata(
    script: str,
    *,
    dialect: str = "tsql",
    seed: int | None = None,
    strict_go: bool = False,
    pretty: bool = True,
    redact_literals: bool = False,
    strip_comments: bool = False,
    redaction_mode: str = "none",
    redaction_policy: str = "all",
    sensitive_columns: set[str] | None = None,
    identifier_vocabulary: IdentifierVocabulary | None = None,
    obfuscate_qualifiers: bool = False,
) -> ObfuscationResult:
    if strict_go:
        _validate_strict_go(script, dialect=dialect)
    redaction_result = apply_redaction(
        script,
        dialect=dialect,
        pretty=pretty,
        redact_literals=redact_literals,
        strip_comments=strip_comments,
        redaction_mode=redaction_mode,
        redaction_policy=redaction_policy,
        sensitive_columns=sensitive_columns,
    )
    redaction_input_sql = redaction_result.output_sql
    profile = get_dialect_profile(dialect)
    registry = IdentifierRegistry(
        profile=profile,
        seed=seed,
        identifier_vocabulary=identifier_vocabulary,
    )
    batches = profile.split_batches(redaction_input_sql)
    transformed_batches: list[str] = []
    statement_anchors: list[dict[str, Any]] = []
    total_statements = 0
    fallback_preserved_statement_count = 0
    next_statement_index = 1
    for batch_idx, batch in enumerate(batches, start=1):
        processed_batch = _process_batch(
            batch,
            dialect=dialect,
            registry=registry,
            profile=profile,
            pretty=pretty,
            batch_number=batch_idx,
            total_batches=len(batches),
            statement_start_index=next_statement_index,
            obfuscate_qualifiers=obfuscate_qualifiers,
        )
        transformed_batches.append(processed_batch.output_sql)
        statement_anchors.extend(processed_batch.statement_anchors)
        total_statements += processed_batch.statement_count
        fallback_preserved_statement_count += processed_batch.fallback_preserved_statement_count
        next_statement_index += processed_batch.statement_count

    output_sql = profile.join_batches(transformed_batches)
    mapping_payload = registry.mapping_payload()
    context_payload = {
        "schema_version": 1,
        "dialect": dialect,
        "seed": seed,
        "pretty": pretty,
        "redact_literals": redact_literals,
        "strip_comments": strip_comments,
        "redaction_mode": redaction_mode,
        "redaction_policy": redaction_policy,
        "obfuscate_qualifiers": obfuscate_qualifiers,
        "sensitive_columns": sorted(sensitive_columns or []),
        "batch_count": len(batches),
        "statement_count": total_statements,
        "mapping_entry_count": len(mapping_payload["entries"]),
        "statement_anchors": statement_anchors,
    }
    fully_transformed_statement_count = max(0, total_statements - fallback_preserved_statement_count)
    privacy_summary = build_privacy_summary(
        sql_text=output_sql,
        dialect=dialect,
        statement_count=total_statements,
        fallback_preserved_statement_count=fallback_preserved_statement_count,
        obfuscated_schema_qualifiers=_mapped_obfuscated_lexemes(
            mapping_payload,
            kind="schema_qualifier",
        ),
        obfuscated_catalog_qualifiers=_mapped_obfuscated_lexemes(
            mapping_payload,
            kind="catalog_qualifier",
        ),
    )
    identifier_surface = privacy_summary.get("identifier_surface", {})
    local_variables = identifier_surface.get("local_variables", {})
    system_variables = identifier_surface.get("system_variables", {})
    user_defined_functions = identifier_surface.get("user_defined_functions", {})
    custom_schema_qualifiers = identifier_surface.get("custom_schema_qualifiers", {})
    common_schema_qualifiers = identifier_surface.get("common_schema_qualifiers", {})
    catalog_qualifiers = identifier_surface.get("catalog_qualifiers", {})
    obfuscation_report = {
        "schema_version": 1,
        "batch_count": len(batches),
        "statement_count": total_statements,
        "statement_anchor_count": len(statement_anchors),
        "fully_transformed_statement_count": fully_transformed_statement_count,
        "fallback_preserved_statement_count": fallback_preserved_statement_count,
        "llm_safe_approved": not bool(privacy_summary.get("llm_safe_blocked", False)),
        "privacy_review_required": bool(privacy_summary.get("manual_review_recommended", False)),
        "privacy_blocker_count": len(privacy_summary.get("blockers", [])),
        "privacy_warning_count": len(privacy_summary.get("warnings", [])),
        "visible_local_variable_count": local_variables.get("occurrence_count", 0),
        "visible_system_variable_count": system_variables.get("occurrence_count", 0),
        "visible_user_defined_function_count": user_defined_functions.get("occurrence_count", 0),
        "visible_custom_schema_qualifier_count": custom_schema_qualifiers.get("occurrence_count", 0),
        "visible_common_schema_qualifier_count": common_schema_qualifiers.get("occurrence_count", 0),
        "visible_catalog_qualifier_count": catalog_qualifiers.get("occurrence_count", 0),
        "redaction_mode": redaction_mode,
        **redaction_result.summary,
    }
    return ObfuscationResult(
        output_sql=output_sql,
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        redaction_payload=redaction_result.redaction_payload,
        obfuscation_report=obfuscation_report,
        privacy_summary=privacy_summary,
    )


def _mapped_obfuscated_lexemes(mapping_payload: dict[str, Any], *, kind: str) -> set[str]:
    values: set[str] = set()
    for entry in mapping_payload.get("entries", []):
        if not isinstance(entry, dict):
            continue
        occurrences = entry.get("occurrences", [])
        if not isinstance(occurrences, list):
            continue
        if not any(isinstance(occurrence, dict) and occurrence.get("kind") == kind for occurrence in occurrences):
            continue
        obfuscated = entry.get("obfuscated_lexeme")
        if isinstance(obfuscated, str):
            values.add(obfuscated)
    return values
