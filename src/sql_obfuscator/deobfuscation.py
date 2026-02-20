from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError
from sqlglot.expressions import Expression

from .errors import ParseScriptError, WorkspaceError
from .go_batches import join_batches, split_batches


@dataclass
class _ReverseEntry:
    normalized_original: str
    temp_prefix: str
    original_unbracketed: str
    original_was_bracketed: bool
    kinds: set[str]
    occurrences: list[dict[str, Any]]


class _ReverseResolver:
    def __init__(self, mapping_payload: dict[str, Any]) -> None:
        self._by_obfuscated: dict[str, list[_ReverseEntry]] = {}
        for entry in mapping_payload.get("entries", []):
            occurrences = entry.get("occurrences", [])
            kinds = {
                occ.get("kind")
                for occ in occurrences
                if isinstance(occ, dict) and isinstance(occ.get("kind"), str)
            }
            reverse_entry = _ReverseEntry(
                normalized_original=entry["normalized_original"],
                temp_prefix=entry["temp_prefix"],
                original_unbracketed=entry["original_unbracketed"],
                original_was_bracketed=entry["original_was_bracketed"],
                kinds=kinds,
                occurrences=occurrences,
            )
            self._by_obfuscated.setdefault(entry["obfuscated_lexeme"], []).append(reverse_entry)

    def resolve(
        self,
        obfuscated_lexeme: str,
        *,
        kind: str,
        batch_index: int,
        statement_index: int,
    ) -> _ReverseEntry | None:
        candidates = self._by_obfuscated.get(obfuscated_lexeme, [])
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        by_kind = [candidate for candidate in candidates if kind in candidate.kinds]
        if len(by_kind) == 1:
            return by_kind[0]
        if by_kind:
            candidates = by_kind

        by_scope = []
        for candidate in candidates:
            if any(
                occ.get("batch_index") == batch_index
                and occ.get("statement_index") == statement_index
                for occ in candidate.occurrences
                if isinstance(occ, dict)
            ):
                by_scope.append(candidate)
        if len(by_scope) == 1:
            return by_scope[0]
        return None

    def candidates(self, obfuscated_lexeme: str) -> list[_ReverseEntry]:
        return self._by_obfuscated.get(obfuscated_lexeme, [])


def _is_update_alias_target(table: exp.Table) -> bool:
    if not isinstance(table.parent, exp.Update) or table.arg_key != "this":
        return False
    table_name = table.this
    if not isinstance(table_name, exp.Identifier):
        return False
    alias_names = {
        alias.this.name
        for alias in table.parent.find_all(exp.TableAlias)
        if isinstance(alias.this, exp.Identifier)
    }
    return table_name.name in alias_names


def _raw_table_name(identifier: exp.Identifier) -> str:
    prefix = ""
    if identifier.args.get("global_"):
        prefix = "##"
    elif identifier.args.get("temporary"):
        prefix = "#"
    return f"{prefix}{identifier.name}"


def _set_identifier(identifier: exp.Identifier, original: _ReverseEntry) -> None:
    identifier.set("this", _strip_temp_prefix(original.original_unbracketed, original.temp_prefix))
    if original.original_was_bracketed:
        identifier.set("quoted", True)


def _strip_temp_prefix(value: str, temp_prefix: str) -> str:
    if temp_prefix and value.startswith(temp_prefix):
        return value[len(temp_prefix):]
    return value


def _record_unknown(
    report: dict[str, Any], *, value: str, kind: str, batch_index: int, statement_index: int
) -> None:
    report["unknown_identifiers"].append(
        {
            "obfuscated": value,
            "kind": kind,
            "batch_index": batch_index,
            "statement_index": statement_index,
        }
    )


def _record_ambiguous(
    report: dict[str, Any],
    *,
    value: str,
    kind: str,
    batch_index: int,
    statement_index: int,
    candidate_count: int,
) -> None:
    report["ambiguous_identifiers"].append(
        {
            "obfuscated": value,
            "kind": kind,
            "batch_index": batch_index,
            "statement_index": statement_index,
            "candidate_count": candidate_count,
        }
    )


def _resolve_and_apply(
    resolver: _ReverseResolver,
    *,
    report: dict[str, Any],
    identifier: exp.Identifier,
    obfuscated_lexeme: str,
    kind: str,
    batch_index: int,
    statement_index: int,
) -> _ReverseEntry | None:
    resolved = resolver.resolve(
        obfuscated_lexeme,
        kind=kind,
        batch_index=batch_index,
        statement_index=statement_index,
    )
    if resolved is None:
        candidates = resolver.candidates(obfuscated_lexeme)
        if candidates:
            _record_ambiguous(
                report,
                value=obfuscated_lexeme,
                kind=kind,
                batch_index=batch_index,
                statement_index=statement_index,
                candidate_count=len(candidates),
            )
        else:
            _record_unknown(
                report,
                value=obfuscated_lexeme,
                kind=kind,
                batch_index=batch_index,
                statement_index=statement_index,
            )
        return None
    _set_identifier(identifier, resolved)
    report["mapped_identifiers"] += 1
    return resolved


def _transform_statement(
    statement: Expression,
    *,
    resolver: _ReverseResolver,
    report: dict[str, Any],
    batch_index: int,
    statement_index: int,
) -> Expression:
    def _transform(node: Expression) -> Expression:
        if isinstance(node, exp.Table):
            identifier = node.this
            if not isinstance(identifier, exp.Identifier):
                return node
            kind = "alias" if _is_update_alias_target(node) else "table"
            _resolve_and_apply(
                resolver,
                report=report,
                identifier=identifier,
                obfuscated_lexeme=_raw_table_name(identifier),
                kind=kind,
                batch_index=batch_index,
                statement_index=statement_index,
            )
            return node

        if isinstance(node, exp.Column):
            column_id = node.this
            if isinstance(column_id, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    identifier=column_id,
                    obfuscated_lexeme=column_id.name,
                    kind="column",
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            qualifier = node.args.get("table")
            if isinstance(qualifier, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    identifier=qualifier,
                    obfuscated_lexeme=qualifier.name,
                    kind="alias",
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            return node

        if isinstance(node, exp.CTE):
            alias = node.args.get("alias")
            if isinstance(alias, exp.TableAlias) and isinstance(alias.this, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    identifier=alias.this,
                    obfuscated_lexeme=alias.this.name,
                    kind="cte",
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            return node

        if isinstance(node, exp.TableAlias):
            if isinstance(node.parent, exp.CTE):
                return node
            if isinstance(node.this, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    identifier=node.this,
                    obfuscated_lexeme=node.this.name,
                    kind="alias",
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            for identifier in node.args.get("columns") or []:
                if isinstance(identifier, exp.Identifier):
                    _resolve_and_apply(
                        resolver,
                        report=report,
                        identifier=identifier,
                        obfuscated_lexeme=identifier.name,
                        kind="column_alias",
                        batch_index=batch_index,
                        statement_index=statement_index,
                    )
            return node

        if isinstance(node, exp.Alias):
            alias_identifier = node.args.get("alias")
            if isinstance(alias_identifier, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    identifier=alias_identifier,
                    obfuscated_lexeme=alias_identifier.name,
                    kind="column_alias",
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            return node

        if isinstance(node, exp.ColumnDef):
            if isinstance(node.this, exp.Identifier):
                resolved = _resolve_and_apply(
                    resolver,
                    report=report,
                    identifier=node.this,
                    obfuscated_lexeme=node.this.name,
                    kind="column_def",
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
                if resolved is not None:
                    _restore_column_def_type_lexeme(
                        node,
                        resolved,
                        batch_index=batch_index,
                        statement_index=statement_index,
                    )
            return node

        if isinstance(node, exp.Schema):
            if not isinstance(node.parent, exp.Insert) or node.arg_key != "this":
                return node
            for identifier in node.expressions:
                if isinstance(identifier, exp.Identifier):
                    _resolve_and_apply(
                        resolver,
                        report=report,
                        identifier=identifier,
                        obfuscated_lexeme=identifier.name,
                        kind="insert_column",
                        batch_index=batch_index,
                        statement_index=statement_index,
                    )
            return node

        return node

    return statement.transform(_transform, copy=True)


def _restore_column_def_type_lexeme(
    column_def: exp.ColumnDef,
    resolved: _ReverseEntry,
    *,
    batch_index: int,
    statement_index: int,
) -> None:
    kind = column_def.args.get("kind")
    if not isinstance(kind, exp.DataType):
        return

    type_lexeme = _find_type_lexeme(
        resolved,
        batch_index=batch_index,
        statement_index=statement_index,
    )
    if not type_lexeme:
        return
    kind.set("this", type_lexeme)


def _find_type_lexeme(
    resolved: _ReverseEntry,
    *,
    batch_index: int,
    statement_index: int,
) -> str | None:
    for occurrence in resolved.occurrences:
        if not isinstance(occurrence, dict):
            continue
        if occurrence.get("kind") != "column_def":
            continue
        if occurrence.get("batch_index") != batch_index:
            continue
        if occurrence.get("statement_index") != statement_index:
            continue
        value = occurrence.get("type_lexeme")
        if isinstance(value, str) and value:
            return value
    return None


def deobfuscate_sql_with_report(
    script: str,
    *,
    mapping_payload: dict[str, Any],
    context_payload: dict[str, Any],
    pretty: bool | None = None,
) -> tuple[str, dict[str, Any]]:
    if mapping_payload.get("schema_version") != 1:
        raise WorkspaceError("Unsupported mapping schema version.")
    if context_payload.get("schema_version") != 1:
        raise WorkspaceError("Unsupported context schema version.")

    dialect = context_payload.get("dialect", "tsql")
    if pretty is None:
        pretty = bool(context_payload.get("pretty", True))

    resolver = _ReverseResolver(mapping_payload)
    report: dict[str, Any] = {
        "mapped_identifiers": 0,
        "unknown_identifiers": [],
        "ambiguous_identifiers": [],
        "batch_count": 0,
        "statement_count": 0,
    }

    output_batches: list[str] = []
    batches = split_batches(script)
    report["batch_count"] = len(batches)

    for batch_index, batch_sql in enumerate(batches, start=1):
        if not batch_sql.strip():
            output_batches.append(batch_sql)
            continue
        try:
            statements = parse(batch_sql, dialect=dialect)
        except ParseError as exc:
            raise ParseScriptError(
                f"Parse error during de-obfuscation in batch {batch_index}/{len(batches)}: {exc}"
            ) from exc
        report["statement_count"] += len(statements)
        transformed: list[Expression] = []
        for statement_index, statement in enumerate(statements, start=1):
            transformed.append(
                _transform_statement(
                    statement,
                    resolver=resolver,
                    report=report,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            )
        output_batches.append(
            ";\n".join(stmt.sql(dialect=dialect, pretty=pretty) for stmt in transformed)
        )

    output_sql = join_batches(output_batches)
    report["unknown_count"] = len(report["unknown_identifiers"])
    report["ambiguous_count"] = len(report["ambiguous_identifiers"])
    report["unknown_by_kind"] = _count_by_kind(report["unknown_identifiers"])
    report["ambiguous_by_kind"] = _count_by_kind(report["ambiguous_identifiers"])
    report["recommendations"] = _recommendations(report)
    return output_sql, report


def _count_by_kind(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        kind = item.get("kind")
        if not isinstance(kind, str):
            continue
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _recommendations(report: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    if report.get("unknown_count", 0) > 0:
        recommendations.append(
            "Unknown identifiers were found. Ensure the LLM did not introduce new names "
            "or rename obfuscated identifiers."
        )
    if report.get("ambiguous_count", 0) > 0:
        recommendations.append(
            "Ambiguous identifier mappings were found. Keep alias/table structure closer "
            "to the obfuscated input or reduce alias rewrites."
        )
    if not recommendations:
        recommendations.append("No unresolved identifiers detected.")
    return recommendations
