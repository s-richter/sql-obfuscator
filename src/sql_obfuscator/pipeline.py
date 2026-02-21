from __future__ import annotations

from dataclasses import dataclass

from sqlglot import parse
from sqlglot.errors import ParseError

from .dialects_base import DialectProfile
from .dialects_factory import get_dialect_profile
from .errors import ParseScriptError
from .redaction import apply_redaction
from .registry import IdentifierRegistry
from .transformer import transform_statements


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
) -> str:
    if not batch_sql.strip():
        return batch_sql

    try:
        statements = parse(batch_sql, dialect=dialect)
    except ParseError as exc:
        error_msg = _format_parse_error(
            exc, batch_sql, batch_number, total_batches)
        raise ParseScriptError(error_msg) from exc

    transformed = transform_statements(
        statements,
        registry=registry,
        batch_index=batch_number,
        batch_sql=batch_sql,
        dialect=dialect,
        profile=profile,
    )
    return ";\n".join(
        stmt.sql(dialect=dialect, pretty=pretty) for stmt in transformed
    )


@dataclass
class ObfuscationResult:
    output_sql: str
    mapping_payload: dict
    context_payload: dict
    redaction_payload: dict | None = None


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
) -> ObfuscationResult:
    del strict_go  # reserved for future strict GO edge-case handling
    profile = get_dialect_profile(dialect)
    registry = IdentifierRegistry(profile=profile, seed=seed)
    batches = profile.split_batches(script)
    transformed_batches = []
    total_statements = 0
    for batch_idx, batch in enumerate(batches, start=1):
        transformed_batch = _process_batch(
            batch,
            dialect=dialect,
            registry=registry,
            profile=profile,
            pretty=pretty,
            batch_number=batch_idx,
            total_batches=len(batches),
        )
        transformed_batches.append(transformed_batch)
        if batch.strip():
            total_statements += len(parse(batch, dialect=dialect))

    output_sql = profile.join_batches(transformed_batches)
    redaction_result = apply_redaction(
        output_sql,
        dialect=dialect,
        pretty=pretty,
        redact_literals=redact_literals,
        strip_comments=strip_comments,
        redaction_mode=redaction_mode,
    )
    output_sql = redaction_result.output_sql
    mapping_payload = registry.mapping_payload()
    context_payload = {
        "schema_version": 1,
        "dialect": dialect,
        "seed": seed,
        "pretty": pretty,
        "redact_literals": redact_literals,
        "strip_comments": strip_comments,
        "redaction_mode": redaction_mode,
        "batch_count": len(batches),
        "statement_count": total_statements,
        "mapping_entry_count": len(mapping_payload["entries"]),
    }
    return ObfuscationResult(
        output_sql=output_sql,
        mapping_payload=mapping_payload,
        context_payload=context_payload,
        redaction_payload=redaction_result.redaction_payload,
    )
