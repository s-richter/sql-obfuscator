from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlglot import exp
from sqlglot.errors import ParseError

from .sqlglot_compat import parse_sql

PRIVACY_SUMMARY_SCHEMA_VERSION = 1

_COMMON_SAFE_SCHEMAS_BY_DIALECT = {
    "tsql": {"dbo", "sys", "information_schema"},
    "hive": {"default", "information_schema"},
}


@dataclass
class _SurfaceBucket:
    occurrence_count: int = 0
    seen: set[str] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)

    def add(self, value: str) -> None:
        normalized = value.strip()
        if not normalized:
            return
        self.occurrence_count += 1
        if normalized in self.seen:
            return
        self.seen.add(normalized)
        if len(self.examples) < 10:
            self.examples.append(normalized)

    def payload(self) -> dict[str, Any]:
        return {
            "occurrence_count": self.occurrence_count,
            "unique_count": len(self.seen),
            "examples": self.examples,
        }


@dataclass
class _PrivacySurface:
    local_variables: _SurfaceBucket = field(default_factory=_SurfaceBucket)
    system_variables: _SurfaceBucket = field(default_factory=_SurfaceBucket)
    user_defined_functions: _SurfaceBucket = field(default_factory=_SurfaceBucket)
    custom_schema_qualifiers: _SurfaceBucket = field(default_factory=_SurfaceBucket)
    common_schema_qualifiers: _SurfaceBucket = field(default_factory=_SurfaceBucket)
    catalog_qualifiers: _SurfaceBucket = field(default_factory=_SurfaceBucket)

    def payload(self) -> dict[str, Any]:
        return {
            "local_variables": self.local_variables.payload(),
            "system_variables": self.system_variables.payload(),
            "user_defined_functions": self.user_defined_functions.payload(),
            "custom_schema_qualifiers": self.custom_schema_qualifiers.payload(),
            "common_schema_qualifiers": self.common_schema_qualifiers.payload(),
            "catalog_qualifiers": self.catalog_qualifiers.payload(),
        }


def build_privacy_summary(
    *,
    sql_text: str,
    dialect: str,
    statement_count: int,
    fallback_preserved_statement_count: int,
) -> dict[str, Any]:
    try:
        statements = parse_sql(sql_text, dialect=dialect)
    except ParseError as exc:
        blockers = [
            "The privacy audit could not parse the obfuscated output for a full identifier-surface check. "
            "Treat the script as review-required before external LLM sharing."
        ]
        return {
            "schema_version": PRIVACY_SUMMARY_SCHEMA_VERSION,
            "dialect": dialect,
            "statement_count": statement_count,
            "analyzed_statement_count": 0,
            "fallback_preserved_statement_count": fallback_preserved_statement_count,
            "llm_safe_blocked": True,
            "manual_review_recommended": True,
            "blocking_identifier_classes": ["privacy_audit_parse_error"],
            "warning_identifier_classes": [],
            "identifier_surface": _PrivacySurface().payload(),
            "blockers": blockers,
            "warnings": [],
            "recommendations": blockers,
            "analysis_error": str(exc),
        }

    surface = _PrivacySurface()
    analyzed_statement_count = 0
    for statement in statements:
        if isinstance(statement.meta.get("raw_sql"), str):
            continue
        analyzed_statement_count += 1
        _collect_statement_surface(statement=statement, dialect=dialect, surface=surface)

    blockers: list[str] = []
    warnings: list[str] = []
    blocking_identifier_classes: list[str] = []
    warning_identifier_classes: list[str] = []

    if fallback_preserved_statement_count > 0:
        blockers.append(
            _format_surface_message(
                count=fallback_preserved_statement_count,
                singular="statement was preserved via parser compatibility fallback/raw passthrough and may still expose identifiers or literals",
                plural="statements were preserved via parser compatibility fallback/raw passthrough and may still expose identifiers or literals",
                examples=[],
            )
        )
        blocking_identifier_classes.append("fallback_preserved_statements")

    if surface.local_variables.occurrence_count > 0:
        blockers.append(
            _format_surface_message(
                count=surface.local_variables.occurrence_count,
                singular="local variable reference remains visible in obfuscated SQL",
                plural="local variable references remain visible in obfuscated SQL",
                examples=surface.local_variables.examples,
            )
        )
        blocking_identifier_classes.append("local_variables")

    if surface.user_defined_functions.occurrence_count > 0:
        blockers.append(
            _format_surface_message(
                count=surface.user_defined_functions.occurrence_count,
                singular="user-defined function name remains visible in obfuscated SQL",
                plural="user-defined function names remain visible in obfuscated SQL",
                examples=surface.user_defined_functions.examples,
            )
        )
        blocking_identifier_classes.append("user_defined_functions")

    if surface.custom_schema_qualifiers.occurrence_count > 0:
        blockers.append(
            _format_surface_message(
                count=surface.custom_schema_qualifiers.occurrence_count,
                singular="custom schema qualifier remains visible in obfuscated SQL",
                plural="custom schema qualifiers remain visible in obfuscated SQL",
                examples=surface.custom_schema_qualifiers.examples,
            )
        )
        blocking_identifier_classes.append("custom_schema_qualifiers")

    if surface.catalog_qualifiers.occurrence_count > 0:
        blockers.append(
            _format_surface_message(
                count=surface.catalog_qualifiers.occurrence_count,
                singular="catalog qualifier remains visible in obfuscated SQL",
                plural="catalog qualifiers remain visible in obfuscated SQL",
                examples=surface.catalog_qualifiers.examples,
            )
        )
        blocking_identifier_classes.append("catalog_qualifiers")

    if surface.system_variables.occurrence_count > 0:
        warnings.append(
            _format_surface_message(
                count=surface.system_variables.occurrence_count,
                singular="system variable remains visible in obfuscated SQL",
                plural="system variables remain visible in obfuscated SQL",
                examples=surface.system_variables.examples,
            )
        )
        warning_identifier_classes.append("system_variables")

    if surface.common_schema_qualifiers.occurrence_count > 0:
        warnings.append(
            _format_surface_message(
                count=surface.common_schema_qualifiers.occurrence_count,
                singular="common schema qualifier remains visible in obfuscated SQL",
                plural="common schema qualifiers remain visible in obfuscated SQL",
                examples=surface.common_schema_qualifiers.examples,
            )
        )
        warning_identifier_classes.append("common_schema_qualifiers")

    if fallback_preserved_statement_count > 0:
        warnings.append(
            "Detailed identifier-surface auditing excludes fallback-preserved statements because they bypass the normal AST transform path."
        )

    recommendations = [*blockers, *warnings]
    if not recommendations:
        recommendations.append("No additional privacy-surface warnings detected in fully transformed statements.")

    return {
        "schema_version": PRIVACY_SUMMARY_SCHEMA_VERSION,
        "dialect": dialect,
        "statement_count": statement_count,
        "analyzed_statement_count": analyzed_statement_count,
        "fallback_preserved_statement_count": fallback_preserved_statement_count,
        "llm_safe_blocked": bool(blockers),
        "manual_review_recommended": bool(blockers or warnings),
        "blocking_identifier_classes": blocking_identifier_classes,
        "warning_identifier_classes": warning_identifier_classes,
        "identifier_surface": surface.payload(),
        "blockers": blockers,
        "warnings": warnings,
        "recommendations": recommendations,
    }


def _collect_statement_surface(*, statement: exp.Expression, dialect: str, surface: _PrivacySurface) -> None:
    for node in statement.walk():
        if isinstance(node, exp.Parameter) and not isinstance(node.parent, exp.Parameter):
            value = node.sql(dialect=dialect)
            if value.startswith("@@"):
                surface.system_variables.add(value)
            else:
                surface.local_variables.add(value)
            continue

        if isinstance(node, exp.Anonymous):
            function_name = str(node.this)
            qualifier = _qualified_function_schema(node)
            if qualifier is not None:
                function_name = f"{qualifier}.{function_name}"
                _record_schema_value(
                    value=qualifier,
                    dialect=dialect,
                    common_bucket=surface.common_schema_qualifiers,
                    custom_bucket=surface.custom_schema_qualifiers,
                )
            surface.user_defined_functions.add(function_name)
            continue

        if isinstance(node, (exp.Table, exp.Column)):
            schema_identifier = node.args.get("db")
            if isinstance(schema_identifier, exp.Identifier):
                _record_schema_value(
                    value=schema_identifier.sql(dialect=dialect),
                    dialect=dialect,
                    common_bucket=surface.common_schema_qualifiers,
                    custom_bucket=surface.custom_schema_qualifiers,
                )
            catalog_identifier = node.args.get("catalog")
            if isinstance(catalog_identifier, exp.Identifier):
                surface.catalog_qualifiers.add(catalog_identifier.sql(dialect=dialect))


def _qualified_function_schema(node: exp.Anonymous) -> str | None:
    parent = node.parent
    if not isinstance(parent, exp.Dot) or parent.expression is not node:
        return None
    qualifier = parent.this
    if isinstance(qualifier, exp.Identifier):
        return qualifier.name
    return None


def _record_schema_value(
    *,
    value: str,
    dialect: str,
    common_bucket: _SurfaceBucket,
    custom_bucket: _SurfaceBucket,
) -> None:
    normalized = value.strip()
    if not normalized:
        return
    if normalized.lower() in _COMMON_SAFE_SCHEMAS_BY_DIALECT.get(dialect.lower(), set()):
        common_bucket.add(normalized)
        return
    custom_bucket.add(normalized)


def _format_surface_message(*, count: int, singular: str, plural: str, examples: list[str]) -> str:
    noun = singular if count == 1 else plural
    if examples:
        sample_text = ", ".join(examples[:3])
        return f"{count} {noun}: {sample_text}."
    return f"{count} {noun}."
