from __future__ import annotations

from collections.abc import Sequence

from sqlglot import Tokenizer, exp
from sqlglot.expressions import Expression

from .dialects_base import DialectProfile
from .identifier_occurrences import (
    column_identifier_occurrences,
    identifier_raw,
    node_context,
    qualified_function_schema_occurrence,
    qualifier_identifier_occurrences,
    table_identifier_occurrence,
)
from .registry import IdentifierRegistry


def _rename_table(
    table: exp.Table,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.Table:
    occurrence = table_identifier_occurrence(
        table,
        profile=profile,
        batch_index=batch_index,
        statement_index=statement_index,
    )
    if occurrence is None:
        return table

    renamed = registry.get_or_create(
        occurrence.lexeme,
        kind=occurrence.kind,
        role=occurrence.role,
        **occurrence.context.as_registry_kwargs(),
    )
    if occurrence.kind == "alias":
        # UPDATE alias target should follow alias obfuscation, not table-name obfuscation.
        occurrence.identifier.set("this", renamed)
        return table

    occurrence.identifier.set("this", profile.table_identifier_ast_value(renamed))
    return table


def _rename_column(
    column: exp.Column,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.Column:
    for occurrence in column_identifier_occurrences(
        column,
        profile=profile,
        batch_index=batch_index,
        statement_index=statement_index,
    ):
        occurrence.identifier.set(
            "this",
            registry.get_or_create(
                occurrence.lexeme,
                kind=occurrence.kind,
                role=occurrence.role,
                **occurrence.context.as_registry_kwargs(),
            ),
        )
    return column


def _rename_cte(
    cte: exp.CTE,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.CTE:
    context = node_context(cte, batch_index=batch_index, statement_index=statement_index)
    alias = cte.args.get("alias")
    if not isinstance(alias, exp.TableAlias) or not isinstance(alias.this, exp.Identifier):
        return cte
    alias.this.set(
        "this",
        registry.get_or_create(
            identifier_raw(alias.this, profile=profile) or alias.this.name,
            kind="cte",
            role="cte_alias",
            **context.as_registry_kwargs(),
        ),
    )
    return cte


def _rename_table_alias(
    table_alias: exp.TableAlias,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.TableAlias:
    context = node_context(table_alias, batch_index=batch_index, statement_index=statement_index)
    # CTE declaration alias is handled in _rename_cte.
    if isinstance(table_alias.parent, exp.CTE):
        return table_alias

    alias_identifier = table_alias.this
    if isinstance(alias_identifier, exp.Identifier):
        alias_identifier.set(
            "this",
            registry.get_or_create(
                identifier_raw(alias_identifier, profile=profile) or alias_identifier.name,
                kind="alias",
                role="table_alias",
                **context.as_registry_kwargs(),
            ),
        )

    for identifier in table_alias.args.get("columns") or []:
        if isinstance(identifier, exp.Identifier):
            identifier.set(
                "this",
                registry.get_or_create(
                    identifier_raw(identifier, profile=profile) or identifier.name,
                    kind="column_alias",
                    role="table_alias_column",
                    **context.as_registry_kwargs(),
                ),
            )

    return table_alias


def _rename_expression_alias(
    alias: exp.Alias,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.Alias:
    context = node_context(alias, batch_index=batch_index, statement_index=statement_index)
    alias_identifier = alias.args.get("alias")
    if isinstance(alias_identifier, exp.Identifier):
        alias_identifier.set(
            "this",
            registry.get_or_create(
                identifier_raw(alias_identifier, profile=profile) or alias_identifier.name,
                kind="column_alias",
                role="projection_alias",
                **context.as_registry_kwargs(),
            ),
        )
    return alias


def _rename_column_def(
    column_def: exp.ColumnDef,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    batch_index: int,
    statement_index: int,
    type_lexemes_by_start: dict[int, str],
) -> exp.ColumnDef:
    context = node_context(column_def, batch_index=batch_index, statement_index=statement_index)
    identifier = column_def.this
    if not isinstance(identifier, exp.Identifier):
        return column_def
    type_lexeme = _column_def_type_lexeme(column_def, type_lexemes_by_start)
    identifier.set(
        "this",
        registry.get_or_create(
            identifier_raw(identifier, profile=profile) or identifier.name,
            kind="column_def",
            role="column_definition",
            type_lexeme=type_lexeme,
            **context.as_registry_kwargs(),
        ),
    )
    return column_def


def _rename_insert_column_list(
    schema: exp.Schema,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    batch_index: int,
    statement_index: int,
) -> exp.Schema:
    context = node_context(schema, batch_index=batch_index, statement_index=statement_index)
    if not isinstance(schema.parent, exp.Insert) or schema.arg_key != "this":
        return schema
    for identifier in schema.expressions:
        if isinstance(identifier, exp.Identifier):
            identifier.set(
                "this",
                registry.get_or_create(
                    identifier_raw(identifier, profile=profile) or identifier.name,
                    kind="insert_column",
                    role="insert_target_column",
                    **context.as_registry_kwargs(),
                ),
            )
    return schema


def transform_statements(
    statements: Sequence[Expression],
    *,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    batch_index: int,
    batch_sql: str,
    dialect: str,
    obfuscate_qualifiers: bool = False,
) -> list[Expression]:
    transformed: list[Expression] = []
    type_lexemes_by_start = _column_type_lexemes_by_start(batch_sql, dialect=dialect)

    for statement_index, statement in enumerate(statements, start=1):
        if isinstance(statement.meta.get("raw_sql"), str):
            transformed.append(statement)
            continue

        def _transform(node: Expression) -> Expression:
            if isinstance(node, exp.Table):
                renamed = _rename_table(
                    node,
                    registry,
                    profile,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
                if obfuscate_qualifiers:
                    return _rename_qualifiers(
                        renamed,
                        registry,
                        profile,
                        dialect=dialect,
                        batch_index=batch_index,
                        statement_index=statement_index,
                    )
                return renamed
            if isinstance(node, exp.Column):
                renamed = _rename_column(
                    node,
                    registry,
                    profile,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
                if obfuscate_qualifiers:
                    return _rename_qualifiers(
                        renamed,
                        registry,
                        profile,
                        dialect=dialect,
                        batch_index=batch_index,
                        statement_index=statement_index,
                    )
                return renamed
            if isinstance(node, exp.Dot) and obfuscate_qualifiers:
                return _rename_qualified_function_schema(
                    node,
                    registry,
                    profile,
                    dialect=dialect,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.CTE):
                return _rename_cte(
                    node,
                    registry,
                    profile,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.TableAlias):
                return _rename_table_alias(
                    node,
                    registry,
                    profile,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.Alias):
                return _rename_expression_alias(
                    node,
                    registry,
                    profile,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            if isinstance(node, exp.ColumnDef):
                return _rename_column_def(
                    node,
                    registry,
                    profile,
                    batch_index=batch_index,
                    statement_index=statement_index,
                    type_lexemes_by_start=type_lexemes_by_start,
                )
            if isinstance(node, exp.Schema):
                return _rename_insert_column_list(
                    node,
                    registry,
                    profile,
                    batch_index=batch_index,
                    statement_index=statement_index,
                )
            return node

        transformed.append(statement.transform(_transform, copy=True))

    return transformed


def _rename_qualified_function_schema(
    node: exp.Dot,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    dialect: str,
    batch_index: int,
    statement_index: int,
) -> exp.Dot:
    occurrence = qualified_function_schema_occurrence(
        node,
        profile=profile,
        dialect=dialect,
        batch_index=batch_index,
        statement_index=statement_index,
    )
    if occurrence is None:
        return node
    occurrence.identifier.set(
        "this",
        registry.get_or_create(
            occurrence.lexeme,
            kind=occurrence.kind,
            role=occurrence.role,
            **occurrence.context.as_registry_kwargs(),
        ),
    )
    return node


def _rename_qualifiers(
    node: exp.Table | exp.Column,
    registry: IdentifierRegistry,
    profile: DialectProfile,
    *,
    dialect: str,
    batch_index: int,
    statement_index: int,
) -> exp.Table | exp.Column:
    for occurrence in qualifier_identifier_occurrences(
        node,
        profile=profile,
        dialect=dialect,
        batch_index=batch_index,
        statement_index=statement_index,
    ):
        occurrence.identifier.set(
            "this",
            registry.get_or_create(
                occurrence.lexeme,
                kind=occurrence.kind,
                role=occurrence.role,
                **occurrence.context.as_registry_kwargs(),
            ),
        )
    return node


def _column_type_lexemes_by_start(batch_sql: str, *, dialect: str) -> dict[int, str]:
    tokens = Tokenizer(dialect=dialect).tokenize(batch_sql)
    token_index_by_start = {token.start: idx for idx, token in enumerate(tokens)}
    type_lexemes_by_start: dict[int, str] = {}

    for idx, token in enumerate(tokens):
        if token.text != "(":
            continue

        cursor = idx + 1
        while cursor < len(tokens):
            current = tokens[cursor]
            if current.text == ")":
                break
            if current.text == ",":
                cursor += 1
                continue

            # Expected shape: <column_name> <type_keyword> ...
            column_name_start = current.start
            if cursor + 1 >= len(tokens):
                break
            type_token = tokens[cursor + 1]
            if not _looks_like_type_keyword(type_token.text):
                cursor += 1
                continue

            type_lexemes_by_start[column_name_start] = type_token.text

            cursor += 2
            while cursor < len(tokens):
                tail = tokens[cursor].text
                if tail == "," or tail == ")":
                    break
                cursor += 1
            continue

    # Keep only entries that correspond to real token starts.
    return {
        start: lexeme
        for start, lexeme in type_lexemes_by_start.items()
        if start in token_index_by_start
    }


def _column_def_type_lexeme(
    column_def: exp.ColumnDef,
    type_lexemes_by_start: dict[int, str],
) -> str | None:
    identifier = column_def.this
    if not isinstance(identifier, exp.Identifier):
        return None

    start = identifier.meta.get("start")
    if not isinstance(start, int):
        return None
    return type_lexemes_by_start.get(start)


def _looks_like_type_keyword(value: str) -> bool:
    if not value:
        return False
    return value[0].isalpha() or value[0] in {"[", '"'}
