from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.expressions import Expression

from .dialects_base import DialectProfile
from .dialects_factory import get_dialect_profile
from .errors import ParseScriptError, WorkspaceError
from .sqlglot_compat import emit_sql, join_emitted_statements, parse_sql


@dataclass
class _ReverseEntry:
    normalized_original: str
    temp_prefix: str
    namespace: str
    original_unbracketed: str
    original_was_bracketed: bool
    kinds: set[str]
    occurrences: list[dict[str, Any]]


@dataclass
class _ResolutionOutcome:
    entry: _ReverseEntry
    confidence: int
    pass_name: str
    candidate_count: int


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
                namespace=str(entry.get("namespace", "")),
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
        scope_id: str = "",
        parent_kind: str = "",
        role: str = "",
        statement_kind: str = "",
        clause_kind: str = "",
        node_kind: str = "",
        arg_key: str = "",
    ) -> _ResolutionOutcome | None:
        candidates = self._by_obfuscated.get(obfuscated_lexeme, [])
        if not candidates:
            return None

        by_kind = [candidate for candidate in candidates if kind in candidate.kinds]
        if not by_kind:
            return None

        strict = [
            candidate
            for candidate in by_kind
            if self._has_occurrence(
                candidate,
                batch_index=batch_index,
                statement_index=statement_index,
                scope_id=scope_id,
                parent_kind=parent_kind,
            )
        ]
        if len(strict) == 1:
            return _ResolutionOutcome(strict[0], confidence=95, pass_name="strict", candidate_count=1)
        if len(strict) > 1:
            scored = self._rank_candidates(
                strict,
                batch_index=batch_index,
                statement_index=statement_index,
                scope_id=scope_id,
                parent_kind=parent_kind,
                role=role,
                statement_kind=statement_kind,
                clause_kind=clause_kind,
                node_kind=node_kind,
                arg_key=arg_key,
            )
            top = self._pick_top(scored)
            if top is not None:
                return _ResolutionOutcome(top, confidence=88, pass_name="strict_scored", candidate_count=len(strict))
            return None

        scoped = [
            candidate
            for candidate in by_kind
            if self._has_occurrence(
                candidate,
                batch_index=batch_index,
                statement_index=statement_index,
            )
        ]
        if len(scoped) == 1:
            return _ResolutionOutcome(scoped[0], confidence=80, pass_name="scoped", candidate_count=1)
        if len(scoped) > 1:
            scored = self._rank_candidates(
                scoped,
                batch_index=batch_index,
                statement_index=statement_index,
                scope_id=scope_id,
                parent_kind=parent_kind,
                role=role,
                statement_kind=statement_kind,
                clause_kind=clause_kind,
                node_kind=node_kind,
                arg_key=arg_key,
            )
            top = self._pick_top(scored)
            if top is not None:
                return _ResolutionOutcome(top, confidence=70, pass_name="scoped_scored", candidate_count=len(scoped))
            return None

        scored = self._rank_candidates(
            by_kind,
            batch_index=batch_index,
            statement_index=statement_index,
            scope_id=scope_id,
            parent_kind=parent_kind,
            role=role,
            statement_kind=statement_kind,
            clause_kind=clause_kind,
            node_kind=node_kind,
            arg_key=arg_key,
        )
        top = self._pick_top(scored)
        if top is None:
            return None
        top_score = 0
        for candidate, score in scored:
            if candidate is top:
                top_score = score
                break
        confidence = max(40, min(75, top_score))
        return _ResolutionOutcome(
            top,
            confidence=confidence,
            pass_name="heuristic",
            candidate_count=len(by_kind),
        )

    def candidates(self, obfuscated_lexeme: str) -> list[_ReverseEntry]:
        return self._by_obfuscated.get(obfuscated_lexeme, [])

    def _has_occurrence(
        self,
        candidate: _ReverseEntry,
        *,
        batch_index: int,
        statement_index: int,
        scope_id: str | None = None,
        parent_kind: str | None = None,
    ) -> bool:
        for occ in candidate.occurrences:
            if not isinstance(occ, dict):
                continue
            if occ.get("batch_index") != batch_index or occ.get("statement_index") != statement_index:
                continue
            if scope_id is not None and occ.get("scope_id") != scope_id:
                continue
            if parent_kind is not None and occ.get("parent_kind") != parent_kind:
                continue
            return True
        return False

    def _rank_candidates(
        self,
        candidates: list[_ReverseEntry],
        *,
        batch_index: int,
        statement_index: int,
        scope_id: str,
        parent_kind: str,
        role: str,
        statement_kind: str,
        clause_kind: str,
        node_kind: str,
        arg_key: str,
    ) -> list[tuple[_ReverseEntry, int]]:
        scores: list[tuple[_ReverseEntry, int]] = []
        for candidate in candidates:
            best = 0
            for occ in candidate.occurrences:
                if not isinstance(occ, dict):
                    continue
                score = 0
                if occ.get("batch_index") == batch_index and occ.get("statement_index") == statement_index:
                    score += 45
                if scope_id and occ.get("scope_id") == scope_id:
                    score += 20
                if parent_kind and occ.get("parent_kind") == parent_kind:
                    score += 12
                if role and occ.get("role") == role:
                    score += 10
                if clause_kind and occ.get("clause_kind") == clause_kind:
                    score += 8
                if statement_kind and occ.get("statement_kind") == statement_kind:
                    score += 6
                if node_kind and occ.get("node_kind") == node_kind:
                    score += 4
                if arg_key and occ.get("arg_key") == arg_key:
                    score += 3
                best = max(best, score)
            scores.append((candidate, best))
        return scores

    def _pick_top(self, scores: list[tuple[_ReverseEntry, int]]) -> _ReverseEntry | None:
        if not scores:
            return None
        top_score = max(score for _, score in scores)
        top = [candidate for candidate, score in scores if score == top_score]
        if len(top) != 1:
            return None
        return top[0]


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


def _is_set_option_column(column: exp.Column) -> bool:
    parent = column.parent
    if not isinstance(parent, exp.EQ):
        return False
    set_item = parent.parent
    if not isinstance(set_item, exp.SetItem):
        return False
    return isinstance(set_item.parent, exp.Set)


def _set_identifier(
    identifier: exp.Identifier,
    original: _ReverseEntry,
    *,
    profile: DialectProfile,
    original_unquoted: str | None = None,
    original_was_quoted: bool | None = None,
) -> None:
    effective_unquoted = original_unquoted
    if effective_unquoted is None:
        effective_unquoted = _strip_temp_prefix(original.original_unbracketed, original.temp_prefix)
    effective_was_quoted = (
        original.original_was_bracketed if original_was_quoted is None else original_was_quoted
    )
    profile.apply_original_quoting(
        identifier,
        original_unquoted=effective_unquoted,
        original_was_quoted=effective_was_quoted,
    )


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


def _record_low_confidence(
    report: dict[str, Any],
    *,
    value: str,
    kind: str,
    batch_index: int,
    statement_index: int,
    confidence: int,
    pass_name: str,
    candidate_count: int,
) -> None:
    report["low_confidence_mappings"].append(
        {
            "obfuscated": value,
            "kind": kind,
            "batch_index": batch_index,
            "statement_index": statement_index,
            "confidence": confidence,
            "pass": pass_name,
            "candidate_count": candidate_count,
        }
    )


def _resolution_context(
    node: Expression,
    *,
    batch_index: int,
    statement_index: int,
) -> dict[str, str | int]:
    parent_kind = type(node.parent).__name__.lower() if isinstance(node.parent, Expression) else ""
    node_kind = type(node).__name__.lower()
    arg_key = node.arg_key or ""
    clause_kind = _clause_kind(node)
    statement_kind = _statement_kind(node)
    return {
        "batch_index": batch_index,
        "statement_index": statement_index,
        "scope_id": f"b{batch_index}.s{statement_index}.{node_kind}.{arg_key}",
        "parent_kind": parent_kind,
        "statement_kind": statement_kind,
        "clause_kind": clause_kind,
        "node_kind": node_kind,
        "arg_key": arg_key,
    }


def _clause_kind(node: Expression) -> str:
    parent = node.parent
    while isinstance(parent, Expression):
        if isinstance(
            parent,
            (
                exp.Select,
                exp.From,
                exp.Where,
                exp.Join,
                exp.Group,
                exp.Order,
                exp.Having,
                exp.Qualify,
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Create,
            ),
        ):
            return type(parent).__name__.lower()
        parent = parent.parent
    return ""


def _statement_kind(node: Expression) -> str:
    parent: Expression | None = node
    while isinstance(parent, Expression):
        if isinstance(
            parent,
            (
                exp.Select,
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Create,
                exp.Merge,
            ),
        ):
            return type(parent).__name__.lower()
        parent = parent.parent
    return ""


def _resolve_and_apply(
    resolver: _ReverseResolver,
    *,
    report: dict[str, Any],
    node: Expression,
    identifier: exp.Identifier,
    obfuscated_lexeme: str,
    kind: str,
    role: str,
    batch_index: int,
    statement_index: int,
    profile: DialectProfile,
    fallback_kinds: tuple[str, ...] = (),
) -> _ReverseEntry | None:
    context = _resolution_context(node, batch_index=batch_index, statement_index=statement_index)
    kinds_to_try = (kind, *fallback_kinds)
    resolved: _ResolutionOutcome | None = None
    resolved_kind = kind
    for candidate_kind in kinds_to_try:
        resolved = resolver.resolve(
            obfuscated_lexeme,
            kind=candidate_kind,
            batch_index=batch_index,
            statement_index=statement_index,
            scope_id=str(context["scope_id"]),
            parent_kind=str(context["parent_kind"]),
            role=role,
            statement_kind=str(context["statement_kind"]),
            clause_kind=str(context["clause_kind"]),
            node_kind=str(context["node_kind"]),
            arg_key=str(context["arg_key"]),
        )
        if resolved is not None:
            resolved_kind = candidate_kind
            break
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
    occurrence_spelling = _resolve_occurrence_spelling(
        resolved.entry,
        kind=kind,
        current_was_quoted=bool(identifier.args.get("quoted")),
        batch_index=batch_index,
        statement_index=statement_index,
        scope_id=str(context["scope_id"]),
        parent_kind=str(context["parent_kind"]),
        role=role,
        statement_kind=str(context["statement_kind"]),
        clause_kind=str(context["clause_kind"]),
        node_kind=str(context["node_kind"]),
        arg_key=str(context["arg_key"]),
    )
    _set_identifier(
        identifier,
        resolved.entry,
        profile=profile,
        original_unquoted=(
            occurrence_spelling["original_unquoted"] if occurrence_spelling is not None else None
        ),
        original_was_quoted=(
            occurrence_spelling["original_was_quoted"] if occurrence_spelling is not None else None
        ),
    )
    report["mapped_identifiers"] += 1
    is_redundant_projection_alias_fallback = kind == "column_alias" and resolved_kind == "column"
    if resolved.confidence < 80 or (resolved_kind != kind and not is_redundant_projection_alias_fallback):
        _record_low_confidence(
            report,
            value=obfuscated_lexeme,
            kind=kind,
            batch_index=batch_index,
            statement_index=statement_index,
            confidence=min(resolved.confidence, 70) if resolved_kind != kind else resolved.confidence,
            pass_name=(
                f"{resolved.pass_name}_fallback_{resolved_kind}"
                if resolved_kind != kind
                else resolved.pass_name
            ),
            candidate_count=resolved.candidate_count,
        )
    return resolved.entry


def _resolve_occurrence_spelling(
    entry: _ReverseEntry,
    *,
    kind: str,
    current_was_quoted: bool,
    batch_index: int,
    statement_index: int,
    scope_id: str,
    parent_kind: str,
    role: str,
    statement_kind: str,
    clause_kind: str,
    node_kind: str,
    arg_key: str,
) -> dict[str, Any] | None:
    candidate_occurrences = [
        occ
        for occ in entry.occurrences
        if isinstance(occ, dict)
        and occ.get("kind") == kind
        and isinstance(occ.get("original_unquoted"), str)
        and isinstance(occ.get("original_was_quoted"), bool)
        and occ.get("original_was_quoted") == current_was_quoted
    ]
    if not candidate_occurrences:
        return None

    scored: list[tuple[dict[str, Any], int]] = []
    for occ in candidate_occurrences:
        score = 0
        if occ.get("batch_index") == batch_index and occ.get("statement_index") == statement_index:
            score += 45
        if scope_id and occ.get("scope_id") == scope_id:
            score += 20
        if parent_kind and occ.get("parent_kind") == parent_kind:
            score += 12
        if role and occ.get("role") == role:
            score += 10
        if clause_kind and occ.get("clause_kind") == clause_kind:
            score += 8
        if statement_kind and occ.get("statement_kind") == statement_kind:
            score += 6
        if node_kind and occ.get("node_kind") == node_kind:
            score += 4
        if arg_key and occ.get("arg_key") == arg_key:
            score += 3
        scored.append((occ, score))

    if not scored:
        return None
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[0][0]


def _transform_statement(
    statement: Expression,
    *,
    resolver: _ReverseResolver,
    report: dict[str, Any],
    batch_index: int,
    statement_index: int,
    profile: DialectProfile,
) -> Expression:
    if isinstance(statement.meta.get("raw_sql"), str):
        return statement

    def _transform(node: Expression) -> Expression:
        if isinstance(node, exp.Table):
            identifier = node.this
            if not isinstance(identifier, exp.Identifier):
                return node
            kind = "alias" if _is_update_alias_target(node) else "table"
            _resolve_and_apply(
                resolver,
                report=report,
                node=node,
                identifier=identifier,
                obfuscated_lexeme=profile.table_identifier_raw(identifier),
                kind=kind,
                role="update_target_alias" if kind == "alias" else "table_reference",
                batch_index=batch_index,
                statement_index=statement_index,
                profile=profile,
            )
            return node

        if isinstance(node, exp.Column):
            if _is_set_option_column(node):
                return node
            column_id = node.this
            if isinstance(column_id, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    node=node,
                    identifier=column_id,
                    obfuscated_lexeme=column_id.name,
                    kind="column",
                    role="column_reference",
                    batch_index=batch_index,
                    statement_index=statement_index,
                    profile=profile,
                )
            qualifier = node.args.get("table")
            if isinstance(qualifier, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    node=node,
                    identifier=qualifier,
                    obfuscated_lexeme=qualifier.name,
                    kind="alias",
                    role="column_qualifier",
                    batch_index=batch_index,
                    statement_index=statement_index,
                    profile=profile,
                )
            return node

        if isinstance(node, exp.CTE):
            alias = node.args.get("alias")
            if isinstance(alias, exp.TableAlias) and isinstance(alias.this, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    node=node,
                    identifier=alias.this,
                    obfuscated_lexeme=alias.this.name,
                    kind="cte",
                    role="cte_alias",
                    batch_index=batch_index,
                    statement_index=statement_index,
                    profile=profile,
                )
            return node

        if isinstance(node, exp.TableAlias):
            if isinstance(node.parent, exp.CTE):
                return node
            if isinstance(node.this, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    node=node,
                    identifier=node.this,
                    obfuscated_lexeme=node.this.name,
                    kind="alias",
                    role="table_alias",
                    batch_index=batch_index,
                    statement_index=statement_index,
                    profile=profile,
                )
            for identifier in node.args.get("columns") or []:
                if isinstance(identifier, exp.Identifier):
                    _resolve_and_apply(
                        resolver,
                        report=report,
                        node=node,
                        identifier=identifier,
                        obfuscated_lexeme=identifier.name,
                        kind="column_alias",
                        role="table_alias_column",
                        batch_index=batch_index,
                        statement_index=statement_index,
                        profile=profile,
                    )
            return node

        if isinstance(node, exp.Alias):
            alias_identifier = node.args.get("alias")
            if isinstance(alias_identifier, exp.Identifier):
                _resolve_and_apply(
                    resolver,
                    report=report,
                    node=node,
                    identifier=alias_identifier,
                    obfuscated_lexeme=alias_identifier.name,
                    kind="column_alias",
                    role="projection_alias",
                    batch_index=batch_index,
                    statement_index=statement_index,
                    profile=profile,
                    fallback_kinds=("column",),
                )
            return node

        if isinstance(node, exp.ColumnDef):
            if isinstance(node.this, exp.Identifier):
                resolved = _resolve_and_apply(
                    resolver,
                    report=report,
                    node=node,
                    identifier=node.this,
                    obfuscated_lexeme=node.this.name,
                    kind="column_def",
                    role="column_definition",
                    batch_index=batch_index,
                    statement_index=statement_index,
                    profile=profile,
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
                        node=node,
                        identifier=identifier,
                        obfuscated_lexeme=identifier.name,
                        kind="insert_column",
                        role="insert_target_column",
                        batch_index=batch_index,
                        statement_index=statement_index,
                        profile=profile,
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
    profile = get_dialect_profile(dialect)
    if pretty is None:
        pretty = bool(context_payload.get("pretty", True))

    resolver = _ReverseResolver(mapping_payload)
    report: dict[str, Any] = {
        "mapped_identifiers": 0,
        "unknown_identifiers": [],
        "ambiguous_identifiers": [],
        "low_confidence_mappings": [],
        "batch_count": 0,
        "statement_count": 0,
    }

    output_batches: list[str] = []
    batches = profile.split_batches(script)
    report["batch_count"] = len(batches)

    for batch_index, batch_sql in enumerate(batches, start=1):
        if not batch_sql.strip():
            output_batches.append(batch_sql)
            continue
        try:
            statements = parse_sql(batch_sql, dialect=dialect)
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
                    profile=profile,
                )
            )
        output_batches.append(
            join_emitted_statements([emit_sql(stmt, dialect=dialect, pretty=pretty) for stmt in transformed])
        )

    output_sql = profile.join_batches(output_batches)
    report["unknown_count"] = len(report["unknown_identifiers"])
    report["ambiguous_count"] = len(report["ambiguous_identifiers"])
    report["low_confidence_count"] = len(report["low_confidence_mappings"])
    report["unknown_by_kind"] = _count_by_kind(report["unknown_identifiers"])
    report["ambiguous_by_kind"] = _count_by_kind(report["ambiguous_identifiers"])
    report["low_confidence_by_kind"] = _count_by_kind(report["low_confidence_mappings"])
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
    if report.get("low_confidence_count", 0) > 0:
        recommendations.append(
            "Some mappings were resolved with low confidence. Review de-obfuscated SQL carefully "
            "or rerun with stricter LLM rewrite constraints."
        )
    if not recommendations:
        recommendations.append("No unresolved identifiers detected.")
    return recommendations
