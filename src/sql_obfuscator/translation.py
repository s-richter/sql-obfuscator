from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlglot import parse
from sqlglot.errors import ParseError

from .dialects_factory import get_dialect_profile
from .errors import ParseScriptError
from .sqlglot_compat import parse_sql


@dataclass
class TranslationResult:
    output_sql: str
    source_dialect: str
    target_dialect: str
    batch_count: int
    statement_count: int
    translated_statement_count: int
    failed_statement_count: int
    warnings: list[str]
    failures: list[dict[str, Any]]
    validated: bool


_QUOTING_MARKERS = ("[", "]", "`", '"')


def _snippet(sql: str, max_length: int = 120) -> str:
    text = sql.strip()
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text


def _warn_on_identifier_shape_change(
    *,
    source_sql: str,
    translated_sql: str,
    batch_index: int,
    statement_index: int,
) -> list[str]:
    source_has_quoting = any(marker in source_sql for marker in _QUOTING_MARKERS)
    translated_has_quoting = any(marker in translated_sql for marker in _QUOTING_MARKERS)
    warnings: list[str] = []
    if source_has_quoting != translated_has_quoting:
        warnings.append(
            "Potential identifier shape change at "
            f"batch {batch_index}, statement {statement_index}: quoting style differs."
        )
    source_upper = bool(re.search(r"\b[A-Z][A-Z0-9_]*\b", source_sql))
    translated_upper = bool(re.search(r"\b[A-Z][A-Z0-9_]*\b", translated_sql))
    if source_upper != translated_upper:
        warnings.append(
            "Potential identifier shape change at "
            f"batch {batch_index}, statement {statement_index}: identifier casing differs."
        )
    return warnings


def translate_sql(
    script: str,
    *,
    source_dialect: str,
    target_dialect: str,
    pretty: bool = True,
    validate: bool = False,
) -> str:
    result = translate_sql_with_report(
        script,
        source_dialect=source_dialect,
        target_dialect=target_dialect,
        pretty=pretty,
        validate=validate,
    )
    if result.failed_statement_count > 0:
        first_failure = result.failures[0]
        raise ParseScriptError(f"Translation failed: {first_failure.get('error', 'unknown error')}")
    return result.output_sql


def translate_sql_with_report(
    script: str,
    *,
    source_dialect: str,
    target_dialect: str,
    pretty: bool = True,
    validate: bool = False,
) -> TranslationResult:
    source_profile = get_dialect_profile(source_dialect)
    target_profile = get_dialect_profile(target_dialect)

    source_sqlglot = source_profile.sqlglot_dialect
    target_sqlglot = target_profile.sqlglot_dialect
    source_batches = source_profile.split_batches(script)

    translated_batches: list[str] = []
    failures: list[dict[str, Any]] = []
    warnings: list[str] = []
    statement_count = 0
    translated_statement_count = 0

    for batch_idx, batch_sql in enumerate(source_batches, start=1):
        if not batch_sql.strip():
            translated_batches.append(batch_sql)
            continue

        try:
            statements = parse_sql(batch_sql, dialect=source_sqlglot, parse_func=parse)
        except ParseError as exc:
            failures.append(
                {
                    "stage": "source_parse",
                    "batch_index": batch_idx,
                    "statement_index": None,
                    "error": str(exc),
                    "snippet": _snippet(batch_sql),
                }
            )
            translated_batches.append(batch_sql)
            continue

        statement_count += len(statements)
        translated_statements: list[str] = []
        for statement_idx, statement in enumerate(statements, start=1):
            try:
                translated_statement = statement.sql(dialect=target_sqlglot, pretty=pretty)
            except Exception as exc:  # sqlglot can raise non-ParseError translation exceptions.
                failures.append(
                    {
                        "stage": "emit",
                        "batch_index": batch_idx,
                        "statement_index": statement_idx,
                        "error": str(exc),
                        "snippet": _snippet(statement.sql(dialect=source_sqlglot, pretty=False)),
                    }
                )
                continue

            translated_statements.append(translated_statement)
            translated_statement_count += 1
            warnings.extend(
                _warn_on_identifier_shape_change(
                    source_sql=statement.sql(dialect=source_sqlglot, pretty=False),
                    translated_sql=translated_statement,
                    batch_index=batch_idx,
                    statement_index=statement_idx,
                )
            )

        translated_batches.append(";\n".join(translated_statements))

    validated = False
    if validate:
        validated = True
        for batch_idx, translated_batch in enumerate(translated_batches, start=1):
            if not translated_batch.strip():
                continue
            try:
                parse_sql(translated_batch, dialect=target_sqlglot, parse_func=parse)
            except ParseError as exc:
                validated = False
                failures.append(
                    {
                        "stage": "validate",
                        "batch_index": batch_idx,
                        "statement_index": None,
                        "error": str(exc),
                        "snippet": _snippet(translated_batch),
                    }
                )

    output_sql = target_profile.join_batches(translated_batches)
    return TranslationResult(
        output_sql=output_sql,
        source_dialect=source_dialect,
        target_dialect=target_dialect,
        batch_count=len(source_batches),
        statement_count=statement_count,
        translated_statement_count=translated_statement_count,
        failed_statement_count=len(failures),
        warnings=warnings,
        failures=failures,
        validated=validated,
    )
